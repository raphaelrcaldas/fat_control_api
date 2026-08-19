"""Rotas do simulador de custo de missão (cálculo puro, sem persistência)"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag
from fcontrol_api.models.shared.estados_cidades import Cidade
from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.schemas.cegep.missoes import (
    CidadePernoiteSchema,
    SimulacaoCombinacaoOut,
    SimulacaoInput,
    SimulacaoOut,
    SimulacaoPernoiteCombOut,
    SimulacaoPernoiteOut,
    SimulacaoValOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, get_current_user
from fcontrol_api.services.custos import (
    calcular_custos_frag_mis,
    carregar_caches_custo,
)
from fcontrol_api.services.custos.integridade import chave_pg_sit
from fcontrol_api.utils.responses import success_response

CENTAVO = Decimal('0.01')

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/missoes', tags=['CEGEP'])

# Tetos de `/simular` (rota sem gate de permissão): o cálculo é dia a dia,
# por combinação, e roda síncrono dentro do handler async. Um ano por
# pernoite e pouco mais que isso no total cobrem qualquer planejamento real
# e mantêm a conta na casa dos milissegundos.
MAX_DIAS_PERNOITE_SIM = 366
MAX_DIAS_SIMULACAO = 400

# Acima deste número de usos na janela a cidade vira "mais usada" (destaque
# no topo da busca). Módulo, não local: o teste do ranking o importa.
MIN_USOS_DESTAQUE = 3


@router.get(
    '/pernoites/cidades',
    response_model=ApiResponse[list[CidadePernoiteSchema]],
    dependencies=[Depends(get_current_user)],
)
async def buscar_cidades_pernoite(
    session: Session,
    active_org: ActiveOrg,
    search: Annotated[str, Query()] = '',
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    dias: Annotated[int, Query(ge=1, le=3650)] = 180,
):
    """Busca cidades para pernoites com ranking por uso recente.

    As cidades mais usadas em pernoites da org ativa (janela dos últimos
    `dias`, por `data_ini`) vêm no topo e marcadas com `mais_usada`. Usa
    OUTER JOIN para preservar cidades nunca usadas (`usos=0`) como opção.

    Sem gate de permissão, como `/simular`: o simulador do FatBird também
    ranqueia a busca de cidade, e o tripulante não tem role. O escopo aqui
    é a **org ativa do próprio token** (`ActiveOrg`), então ninguém enxerga
    uso de outra unidade; o que se expõe é a contagem agregada de pernoites
    da unidade a que o usuário já pertence — sem missão, data ou militar.
    """
    corte = date.today() - timedelta(days=dias)

    usos_sub = (
        select(
            PernoiteFrag.cidade_id.label('cidade_id'),
            func.count(PernoiteFrag.id).label('usos'),
        )
        .join(FragMis, FragMis.id == PernoiteFrag.frag_id)
        .where(
            FragMis.uae == active_org,
            PernoiteFrag.data_ini >= corte,
        )
        .group_by(PernoiteFrag.cidade_id)
        .subquery()
    )

    usos = func.coalesce(usos_sub.c.usos, 0).label('usos')

    stmt = (
        select(Cidade, usos)
        .outerjoin(usos_sub, usos_sub.c.cidade_id == Cidade.codigo)
        .order_by(usos.desc(), Cidade.nome.asc(), Cidade.codigo)
        .limit(limit)
    )

    termo = search.strip()
    if termo:
        stmt = stmt.where(
            func.unaccent(Cidade.nome).ilike(func.unaccent(f'%{termo}%'))
        )

    rows = (await session.execute(stmt)).all()

    data = [
        CidadePernoiteSchema(
            codigo=cidade.codigo,
            nome=cidade.nome,
            uf=cidade.uf,
            usos=total,
            mais_usada=total > MIN_USOS_DESTAQUE,
        )
        for cidade, total in rows
    ]

    return success_response(data=data)


@router.post(
    '/simular',
    response_model=ApiResponse[SimulacaoOut],
    dependencies=[Depends(get_current_user)],
)
async def simular_custo_missao(payload: SimulacaoInput, session: Session):
    """Simula o custo de uma missão planejada, sem persistir nada.

    Reusa o cálculo puro `calcular_custos_frag_mis` sobre as tabelas de
    referência globais (diárias, soldos, grupos), então não há org ativa,
    auditoria nem commit. Os pernoites recebem **IDs sintéticos**
    sequenciais (1-based, na ordem do payload) — uma simulação não tem
    pernoite de banco. `total_dias`/`total_diarias` são **universais** da
    missão (dias para comissionamento não se multiplicam por militar); só
    `subtotal`/`total_geral` escalam pela quantidade de cada combinação.

    **Sem gate de permissão de propósito**, mas com identidade validada: a
    rota é uma calculadora pura sobre tabelas de referência públicas — não
    lê nem escreve dado de organização nenhuma, não recebe identificador de
    recurso e não persiste, então `missoes_cegep.view` só servia para
    quebrar o simulador self-service do FatBird, cujo tripulante não tem
    role. O `get_current_user` continua: o middleware global só confere a
    assinatura do JWT, e é essa dependency que carrega o usuário do banco,
    barra conta inativa e valida o vínculo token↔app_client.
    """
    # 1. Validações estruturais (400 com motivos acumulados). Sem período
    # de missão (afast/regres): só as datas dos pernoites importam — conta
    # rápida. Dia de fronteira compartilhado entre pernoites não é conflito
    # (mesma semântica do cadastro real: comparação estrita).
    erros: list[str] = []

    # O cálculo percorre dia a dia, por combinação: sem teto, um único
    # pernoite de séculos trava o event loop por minutos (a rota é aberta a
    # qualquer autenticado, então o limite é o que impede o DoS trivial).
    total_dias_payload = 0
    for i, p in enumerate(payload.pernoites, start=1):
        if p.data_fim < p.data_ini:
            erros.append(f'- Pernoite {i}: data de fim anterior à de início')
            continue

        dias = (p.data_fim - p.data_ini).days + 1
        total_dias_payload += dias
        if dias > MAX_DIAS_PERNOITE_SIM:
            erros.append(
                f'- Pernoite {i}: período maior que '
                f'{MAX_DIAS_PERNOITE_SIM} dias'
            )

    if total_dias_payload > MAX_DIAS_SIMULACAO:
        erros.append(
            f'- Simulação maior que {MAX_DIAS_SIMULACAO} dias no total'
        )

    for i, p in enumerate(payload.pernoites):
        for outro in payload.pernoites[i + 1 :]:
            if p.data_ini < outro.data_fim and outro.data_ini < p.data_fim:
                erros.append('- Há pernoites com datas sobrepostas')
                break
        else:
            continue
        break

    vistas: set[tuple[str, str]] = set()
    for c in payload.combinacoes:
        chave = (c.p_g.value, c.sit)
        if chave in vistas:
            erros.append(
                f'- Combinação repetida: {c.p_g.value} ({c.sit})'.upper()
            )
        vistas.add(chave)

    if erros:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Corrija os seguintes itens:\n' + '\n'.join(erros),
        )

    # 2. Montar inputs reusando os schemas de custo existentes. Militares
    # entram como combinação única (a função deduplica); a multiplicação
    # por quantidade é feita depois, fora do cálculo.
    frag_input = CustoFragMisInput(acrec_desloc=payload.acrec_desloc)
    users_input = [
        CustoUserFragInput(p_g=c.p_g, sit=c.sit) for c in payload.combinacoes
    ]
    pernoites_input = [
        CustoPernoiteInput(
            id=i + 1,
            data_ini=p.data_ini,
            data_fim=p.data_fim,
            meia_diaria=p.meia_diaria,
            acrec_desloc=p.acrec_desloc,
            cidade_codigo=p.cidade_id,
        )
        for i, p in enumerate(payload.pernoites)
    ]

    # 3. Calcular sobre os caches de referência globais
    (
        valores_cache,
        soldos_cache,
        grupos_pg,
        grupos_cidade,
    ) = await carregar_caches_custo(session)
    custos = calcular_custos_frag_mis(
        frag_input,
        users_input,
        pernoites_input,
        grupos_pg,
        grupos_cidade,
        valores_cache,
        soldos_cache,
    )

    # 4. Totais por combinação: valor_unitario já inclui o R$95 global 1×
    totais_pg_sit: dict = custos.get('totais_pg_sit', {})
    total_geral = Decimal('0')
    combinacoes_out: list[SimulacaoCombinacaoOut] = []
    for c in payload.combinacoes:
        chave = chave_pg_sit(c.p_g, c.sit)
        valor_unit = Decimal(
            str(totais_pg_sit.get(chave, {}).get('total_valor', 0))
        )
        subtotal = (valor_unit * c.qtd).quantize(
            CENTAVO, rounding=ROUND_HALF_UP
        )
        total_geral += subtotal
        combinacoes_out.append(
            SimulacaoCombinacaoOut(
                p_g=c.p_g,
                sit=c.sit,
                qtd=c.qtd,
                valor_unitario=float(valor_unit),
                subtotal=float(subtotal),
            )
        )

    # 5. Extrato por pernoite (lido do JSONB por ID sintético) + varredura
    # de valores zerados (vigência ausente na tabela para a data simulada).
    valores_zerados = False
    pernoites_out: list[SimulacaoPernoiteOut] = []
    for i, p in enumerate(payload.pernoites):
        pnt = custos.get(f'pernoite_{i + 1}', {})
        combs_pnt: list[SimulacaoPernoiteCombOut] = []
        for c in payload.combinacoes:
            bloco = pnt.get(chave_pg_sit(c.p_g, c.sit), {})
            vals = [
                SimulacaoValOut(valor=v['valor'], qtd=v['qtd'])
                for v in bloco.get('vals', [])
            ]
            for v in vals:
                if v.valor == 0 and v.qtd > 0:
                    valores_zerados = True
            combs_pnt.append(
                SimulacaoPernoiteCombOut(
                    p_g=c.p_g,
                    sit=c.sit,
                    vals=vals,
                    subtotal=bloco.get('subtotal', 0),
                )
            )
        pernoites_out.append(
            SimulacaoPernoiteOut(
                indice=i,
                cidade_id=p.cidade_id,
                grupo_cid=pnt.get('grupo_cid', 3),
                data_ini=p.data_ini,
                data_fim=p.data_fim,
                dias=pnt.get('dias', 0),
                ac_desloc=pnt.get('ac_desloc', 0),
                combinacoes=combs_pnt,
            )
        )

    resultado = SimulacaoOut(
        total_geral=float(total_geral),
        total_dias=custos.get('total_dias', 0),
        total_diarias=custos.get('total_diarias', 0),
        acrec_desloc_missao=custos.get('acrec_desloc_missao', 0),
        valores_zerados=valores_zerados,
        combinacoes=combinacoes_out,
        pernoites=pernoites_out,
    )

    return success_response(data=resultado)
