from datetime import date
from decimal import Decimal
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    HeavyCDS,
    Missao,
    OIEtapa,
    PqdEtapa,
    REVOEtapa,
    TipoMissao,
)
from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.indicadores import (
    AeronaveLinha,
    IndicadoresResponse,
    LancamentoLinha,
    MesLinha,
    Metricas,
    PqdTipoLinha,
    RegimeLinha,
    TipoMissaoLinha,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
AnoRef = Annotated[int, Query(ge=2020)]
ViewEtapas = Depends(permission_checker('etapas', 'view'))

router = APIRouter(prefix='/indicadores', tags=['estatistica'])


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[IndicadoresResponse],
)
async def get_indicadores(
    session: Session,
    active_org: ActiveOrg,
    ano_ref: AnoRef,
    _: Annotated[User, ViewEtapas],
    projeto: Annotated[str | None, Query(max_length=2)] = None,
):
    """Painel anual de indicadores das etapas voadas da org ativa.

    Recorte: sempre a org ativa (`Missao.uae`) e, opcionalmente, um
    projeto da frota dela. `projeto=None` significa "todos os projetos"
    — cada tenant opera projetos diferentes, entao o conjunto de
    aeronaves ja sai escopado pela org via `Missao.uae`.

    Etapas de simulador ficam sempre de fora (o painel e de producao
    real). As flags `sagem`/`parte1` nao filtram nada: o painel soma
    tudo que foi registrado.
    """
    # CTE de escopo: uma linha por etapa, nunca mais. Toda agregacao
    # abaixo parte daqui e toca no maximo UMA tabela filha 1:N por vez —
    # do contrario o produto cartesiano entre OIEtapa, PqdEtapa,
    # REVOEtapa e HeavyCDS inflaria carga, pax e comb.
    escopo = (
        select(
            Etapa.id.label('id'),
            Etapa.anv.label('anv'),
            Aeronave.projeto.label('projeto'),
            extract('month', Etapa.data).label('mes'),
            Etapa.tvoo.label('tvoo'),
            Etapa.pousos.label('pousos'),
            Etapa.pax.label('pax'),
            Etapa.carga.label('carga'),
            Etapa.comb.label('comb'),
            Etapa.lub.label('lub'),
        )
        .join(Missao, Missao.id == Etapa.missao_id)
        # 1:1 por matricula — nao duplica a linha da etapa.
        .join(Aeronave, Aeronave.matricula == Etapa.anv)
        .where(
            Missao.uae == active_org,
            Missao.is_simulador.is_(False),
            # `between` no lugar de extract('year', ...): mesmo recorte,
            # mas sargable — nao fecha a porta para um indice futuro.
            Etapa.data.between(
                date(ano_ref, 1, 1),
                date(ano_ref, 12, 31),
            ),
        )
    )

    if projeto:
        escopo = escopo.where(Aeronave.projeto == projeto)

    cte = escopo.cte('etapas_escopo')
    col = cte.c

    # 1. Base mensal: so a propria etapa, sem filha nenhuma.
    base_mes = await session.execute(
        select(
            col.mes,
            func.count().label('etapas'),
            func.coalesce(func.sum(col.tvoo), 0).label('tvoo'),
            func.coalesce(func.sum(col.pousos), 0).label('pousos'),
            func.coalesce(func.sum(col.pax), 0).label('pax'),
            func.coalesce(func.sum(col.carga), 0).label('carga'),
            func.coalesce(func.sum(col.comb), 0).label('comb'),
            func.coalesce(func.sum(col.lub), 0).label('lub'),
        ).group_by(col.mes)
    )

    # 2. PQD lancados: mes x tipo.
    base_pqd = await session.execute(
        select(
            col.mes,
            PqdEtapa.tipo,
            func.coalesce(func.sum(PqdEtapa.qtd), 0).label('qtd'),
        )
        .select_from(PqdEtapa)
        .join(cte, col.id == PqdEtapa.etapa_id)
        .group_by(col.mes, PqdEtapa.tipo)
    )

    # 3. Combustivel transferido (REVO) por mes.
    base_revo = await session.execute(
        select(
            col.mes,
            func.coalesce(func.sum(REVOEtapa.comb_transf), 0).label(
                'comb_transf'
            ),
        )
        .select_from(REVOEtapa)
        .join(cte, col.id == REVOEtapa.etapa_id)
        .group_by(col.mes)
    )

    # 4. Cargas lancadas: mes x tipo (heavy/cds), quantidade e peso.
    base_lanc = await session.execute(
        select(
            col.mes,
            HeavyCDS.tipo,
            func.count().label('qtd'),
            func.coalesce(func.sum(HeavyCDS.peso), 0).label('peso'),
        )
        .select_from(HeavyCDS)
        .join(cte, col.id == HeavyCDS.etapa_id)
        .group_by(col.mes, HeavyCDS.tipo)
    )

    # 5. Quebras por OI. So `OIEtapa.tvoo` pode ser somado aqui: ele ja
    # e o rateio do tempo da etapa entre os OIs (create_etapa valida
    # que a soma fecha com Etapa.tvoo). Carga/pax/comb nao tem rateio.
    base_reg = await session.execute(
        select(
            OIEtapa.reg,
            func.coalesce(func.sum(OIEtapa.tvoo), 0).label('tvoo'),
        )
        .select_from(OIEtapa)
        .join(cte, col.id == OIEtapa.etapa_id)
        .group_by(OIEtapa.reg)
        .order_by(OIEtapa.reg)
    )

    base_tipo_mis = await session.execute(
        select(
            TipoMissao.cod,
            TipoMissao.desc,
            func.coalesce(func.sum(OIEtapa.tvoo), 0).label('tvoo'),
            func.count(func.distinct(col.id)).label('etapas'),
        )
        .select_from(OIEtapa)
        .join(cte, col.id == OIEtapa.etapa_id)
        .join(TipoMissao, TipoMissao.id == OIEtapa.tipo_missao_id)
        .group_by(TipoMissao.cod, TipoMissao.desc)
        .order_by(func.sum(OIEtapa.tvoo).desc(), TipoMissao.cod)
    )

    # 6. Producao por aeronave.
    base_anv = await session.execute(
        select(
            col.anv,
            col.projeto,
            func.count().label('etapas'),
            func.coalesce(func.sum(col.tvoo), 0).label('tvoo'),
            func.coalesce(func.sum(col.pousos), 0).label('pousos'),
            func.coalesce(func.sum(col.carga), 0).label('carga'),
            func.coalesce(func.sum(col.pax), 0).label('pax'),
        )
        .group_by(col.anv, col.projeto)
        .order_by(func.sum(col.tvoo).desc(), col.anv)
    )

    # Indexa por mes; a serie sai sempre com 12 posicoes (o front nunca
    # deve inventar mes faltante).
    por_mes = {int(r.mes): r for r in base_mes.all()}

    pqd_mes: dict[int, int] = {}
    pqd_tipo: dict[str, int] = {}
    for r in base_pqd.all():
        mes = int(r.mes)
        pqd_mes[mes] = pqd_mes.get(mes, 0) + r.qtd
        pqd_tipo[r.tipo] = pqd_tipo.get(r.tipo, 0) + r.qtd

    revo_mes = {int(r.mes): r.comb_transf for r in base_revo.all()}

    heavy_mes: dict[int, int] = {}
    cds_mes: dict[int, int] = {}
    peso_mes: dict[int, int] = {}
    lanc_tipo: dict[str, tuple[int, int]] = {}
    for r in base_lanc.all():
        mes = int(r.mes)
        if r.tipo == 'heavy':
            heavy_mes[mes] = heavy_mes.get(mes, 0) + r.qtd
        else:
            cds_mes[mes] = cds_mes.get(mes, 0) + r.qtd
        peso_mes[mes] = peso_mes.get(mes, 0) + r.peso
        qtd_ant, peso_ant = lanc_tipo.get(r.tipo, (0, 0))
        lanc_tipo[r.tipo] = (qtd_ant + r.qtd, peso_ant + r.peso)

    mensal: list[MesLinha] = []
    for m in range(1, 13):
        linha = por_mes.get(m)
        mensal.append(
            MesLinha(
                mes=m,
                etapas=linha.etapas if linha else 0,
                tvoo=linha.tvoo if linha else 0,
                pousos=linha.pousos if linha else 0,
                pax=linha.pax if linha else 0,
                carga=linha.carga if linha else 0,
                comb=linha.comb if linha else 0,
                lub=linha.lub if linha else Decimal(0),
                pqd=pqd_mes.get(m, 0),
                comb_transf=revo_mes.get(m, 0),
                heavy_qtd=heavy_mes.get(m, 0),
                cds_qtd=cds_mes.get(m, 0),
                peso_lancado=peso_mes.get(m, 0),
            )
        )

    # Totais saem da soma das 12 linhas: nenhuma query extra e, por
    # construcao, o rodape da matriz fecha com os KPIs do topo.
    totais = Metricas(
        etapas=sum(x.etapas for x in mensal),
        tvoo=sum(x.tvoo for x in mensal),
        pousos=sum(x.pousos for x in mensal),
        pax=sum(x.pax for x in mensal),
        carga=sum(x.carga for x in mensal),
        comb=sum(x.comb for x in mensal),
        lub=sum((x.lub for x in mensal), Decimal(0)),
        pqd=sum(x.pqd for x in mensal),
        comb_transf=sum(x.comb_transf for x in mensal),
        heavy_qtd=sum(x.heavy_qtd for x in mensal),
        cds_qtd=sum(x.cds_qtd for x in mensal),
        peso_lancado=sum(x.peso_lancado for x in mensal),
    )

    return success_response(
        data=IndicadoresResponse(
            ano_ref=ano_ref,
            totais=totais,
            mensal=mensal,
            por_regime=[
                RegimeLinha(reg=r.reg, tvoo=r.tvoo) for r in base_reg.all()
            ],
            por_tipo_missao=[
                TipoMissaoLinha(
                    cod=r.cod,
                    desc=r.desc,
                    tvoo=r.tvoo,
                    etapas=r.etapas,
                )
                for r in base_tipo_mis.all()
            ],
            por_aeronave=[
                AeronaveLinha(
                    anv=r.anv,
                    projeto=r.projeto,
                    etapas=r.etapas,
                    tvoo=r.tvoo,
                    pousos=r.pousos,
                    carga=r.carga,
                    pax=r.pax,
                )
                for r in base_anv.all()
            ],
            pqd_por_tipo=[
                PqdTipoLinha(tipo=t, qtd=q)
                for t, q in sorted(
                    pqd_tipo.items(),
                    key=lambda kv: (-kv[1], kv[0]),
                )
            ],
            lancamentos=[
                LancamentoLinha(tipo=t, qtd=v[0], peso=v[1])
                for t, v in sorted(lanc_tipo.items())
            ],
        )
    )
