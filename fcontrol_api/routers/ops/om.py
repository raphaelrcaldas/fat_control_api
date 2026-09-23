"""Router para Ordem de Missão (OM)"""

from datetime import date, datetime, timezone
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, Integer, case, cast, extract, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.om import (
    Etiqueta,
    OrdemEtapa,
    OrdemMissao,
    OrdemTripulacao,
)
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.ops.om import (
    ICAO_CODE_LENGTH,
    OrdemMissaoCreate,
    OrdemMissaoList,
    OrdemMissaoOut,
    OrdemMissaoUpdate,
    RouteSuggestionOut,
)
from fcontrol_api.schemas.response import ApiPaginatedResponse, ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    has_org_permission,
    permission_checker,
)
from fcontrol_api.services.logs import log_user_action, ordem_snapshot
from fcontrol_api.services.om import (
    assert_numero_om_livre,
    criar_tripulacao_batch,
    emitir_numero_om,
    montar_etapa,
    validar_integridade_etapas,
)
from fcontrol_api.utils.responses import paginated_response, success_response
from fcontrol_api.utils.strings import escape_like

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/om', tags=['ordens-missao'])

# Máquina de estados: transições de status permitidas a partir de cada
# status (espelha STATUS_TRANSITIONS do frontend)
STATUS_TRANSITIONS: dict[str, set[str]] = {
    'rascunho': {'aprovada'},
    'aprovada': {'cancelada'},
    'cancelada': set(),
}

# Guardas reutilizáveis. `om_etiquetas.py` repete estes mesmos guardas: as
# etiquetas herdam a permissão da OM (mesmo recurso `ordem_missao`).
CreateOM = Depends(permission_checker('ops.ordem_missao', 'create'))
UpdateOM = Depends(permission_checker('ops.ordem_missao', 'update'))
DeleteOM = Depends(permission_checker('ops.ordem_missao', 'delete'))

# Auditoria. `RESOURCE` repete a string dos `permission_checker` acima de
# propósito: unifica os logs de ação com os `access_denied` que o
# security.py já grava sob o mesmo recurso.
RESOURCE = 'ops.ordem_missao'

# Teto de paginação, igual ao de `list_aeronaves` e `list_missoes`. Os
# limites são cobrados na assinatura (`Query(ge=..., le=...)`), e não com
# um `min`/`max` no corpo: assim um valor fora da faixa devolve 422 em vez
# de ser silenciosamente corrigido, e a faixa aparece no OpenAPI. Sem o
# piso, `per_page=0` chegava a `paginated_response` e estourava
# `ZeroDivisionError` (500) no cálculo de `pages`.
MAX_PER_PAGE = 100


def _dt_dep_date_utc():
    """Dia UTC da decolagem, para comparar com um filtro date-only.

    `cast(timestamptz AS date)` converte pelo **TimeZone da sessão** do
    Postgres, não por UTC. Como o horário de uma OM é Zulu de ponta a
    ponta (o frontend grava `...Z` e lê a data com um split da string),
    herdar o fuso da sessão faria o filtro discordar da célula em que o
    quadro desenha a etapa assim que o servidor não estivesse em UTC —
    uma etapa às 01:00Z cairia no dia anterior e sumiria da janela.
    `timezone('UTC', ...)` crava a conversão e torna o resultado
    independente do ambiente.
    """
    return cast(func.timezone('UTC', OrdemEtapa.dt_dep), Date)


def _data_saida_de(etapas) -> date | None:
    """Dia UTC da primeira decolagem, ou None se não houver etapa.

    `.date()` de um datetime aware devolve o dia **no offset recebido**, não
    em UTC: o mesmo instante `2026-03-12T01:00Z` chega como
    `2026-03-11T22:00-03:00` e viraria dia 11. Como `list_ordens` recorta
    pelo dia UTC (ver `_dt_dep_date_utc`), derivar sem normalizar deixaria
    `data_saida` discordando do dia pelo qual a própria OM é encontrada —
    hoje inofensivo porque o frontend sempre envia `Z`, mas é o tipo de
    acoplamento que quebra em silêncio quando outro cliente aparece.
    """
    if not etapas:
        return None
    return min(e.dt_dep for e in etapas).astimezone(timezone.utc).date()


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiPaginatedResponse[OrdemMissaoList],
)
async def list_ordens(
    session: Session,
    active_org: ActiveOrg,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = 20,
    status: Annotated[list[str] | None, Query()] = None,
    status_ne: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    busca: str | None = None,
    etiquetas_ids: Annotated[list[int] | None, Query()] = None,
    ordem: Annotated[
        Literal['recente', 'cronologica', 'numerica'], Query()
    ] = 'recente',
):
    """
    Lista ordens de missão com filtros e paginação.

    - **status**: Lista de status para incluir
    - **status_ne**: Status para excluir (not equal, ex: rascunho)
    - **data_inicio/data_fim**: Filtro por data de decolagem da primeira etapa
    - **busca**: Busca por número, localidade, tipo ou nome de guerra
    - **ordem**: `recente` (cadastro, padrão), `cronologica` (decolagem) ou
      `numerica` (ano da OM e numeração, decrescente)
    """
    # Query base: ordens da org ativa, não deletadas
    query = select(OrdemMissao).where(
        OrdemMissao.uae == active_org,
        OrdemMissao.deleted_at.is_(None),
    )

    # Filtro por status (inclusão ou exclusão)
    if status:
        query = query.where(OrdemMissao.status.in_(status))
    elif status_ne:
        query = query.where(OrdemMissao.status != status_ne)

    # Filtro por busca (número, ICAO, tipo, ou nome de guerra)
    if busca:
        escaped_busca = escape_like(busca)
        escaped_busca_upper = escape_like(busca.upper())

        # Subquery: ordens com etapas que têm o código ICAO
        busca_pattern = f'%{escaped_busca_upper}%'
        etapas_subquery = (
            select(OrdemEtapa.ordem_id)
            .where(
                (OrdemEtapa.origem.ilike(busca_pattern, escape='\\'))
                | (OrdemEtapa.dest.ilike(busca_pattern, escape='\\'))
            )
            .distinct()
        )

        # Subquery: ordens com tripulantes que têm o nome de guerra
        tripulacao_subquery = (
            select(OrdemTripulacao.ordem_id)
            .join(OrdemTripulacao.tripulante)
            .join(Tripulante.user)
            .where(
                func.unaccent(User.nome_guerra).ilike(
                    func.unaccent(f'%{escaped_busca}%'), escape='\\'
                )
            )
            .distinct()
        )

        query = query.where(
            (OrdemMissao.numero.ilike(f'%{escaped_busca}%', escape='\\'))
            | (OrdemMissao.id.in_(etapas_subquery))
            | (OrdemMissao.tipo.ilike(f'%{escaped_busca}%', escape='\\'))
            | (OrdemMissao.id.in_(tripulacao_subquery))
        )

    # Filtro por data: busca missões que tenham etapas no período
    if data_inicio or data_fim:
        etapas_date_sub = select(OrdemEtapa.ordem_id).distinct()
        if data_inicio:
            etapas_date_sub = etapas_date_sub.where(
                _dt_dep_date_utc() >= data_inicio
            )
        if data_fim:
            etapas_date_sub = etapas_date_sub.where(
                _dt_dep_date_utc() <= data_fim
            )
        query = query.where(OrdemMissao.id.in_(etapas_date_sub))

    # Filtro por etiquetas
    if etiquetas_ids:
        query = query.where(
            OrdemMissao.etiquetas.any(Etiqueta.id.in_(etiquetas_ids))
        )

    # Contagem total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Ordenação. O padrão é o da listagem de OMs: as mais recentes
    # primeiro, por data de cadastro.
    #
    # `cronologica` existe para quem lê o período como uma *janela* — o
    # quadro de operações pede uma semana e a desenha da esquerda para a
    # direita. Ali, ordenar por cadastro faria o corte do `per_page` guardar
    # as OMs cadastradas por último em vez das do início da janela, e uma
    # missão dentro do período sumiria do quadro. É um parâmetro explícito,
    # e não uma consequência de haver filtro de data, porque a listagem
    # também filtra por data e não pode ter a ordem invertida por isso.
    #
    # `numerica` é a ordem como a OM é *identificada*: ano e numeração, que
    # é o par único por UAE (ver `assert_numero_om_livre`). Precisa ser feita
    # aqui, e não no cliente: reordenar só a página já recortada por
    # `created_at` deixa a ordem certa dentro da página e errada entre elas.
    # O ano vem de `data_saida` — a mesma fonte de `emitir_numero_om`. O cast
    # para Integer evita que '1000' venha antes de '999' quando a numeração
    # passar de três dígitos, e a guarda regex protege o cast de 'auto' e de
    # números editados à mão que não sejam numéricos. Sem ano ou sem número
    # utilizável a OM sobe ao topo (NULLS FIRST): é um cadastro incompleto,
    # e esconder no fim da última página é o mesmo que perdê-lo.
    # (id como tiebreaker garante paginação determinística nos três casos)
    if ordem == 'numerica':
        ano_om = extract('year', OrdemMissao.data_saida)
        numero_seq = case(
            (
                OrdemMissao.numero.op('~')('^[0-9]+$'),
                cast(OrdemMissao.numero, Integer),
            ),
            else_=None,
        )
        query = query.order_by(
            ano_om.desc().nullsfirst(),
            numero_seq.desc().nullsfirst(),
            OrdemMissao.id.desc(),
        )
    elif ordem == 'cronologica':
        primeira_dep = (
            select(func.min(OrdemEtapa.dt_dep))
            .where(OrdemEtapa.ordem_id == OrdemMissao.id)
            .scalar_subquery()
        )
        query = query.order_by(primeira_dep.asc(), OrdemMissao.id.asc())
    else:
        query = query.order_by(
            OrdemMissao.created_at.desc(), OrdemMissao.id.desc()
        )

    # Paginação com eager load de etapas
    query = (
        query
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(
            selectinload(OrdemMissao.etapas),
            selectinload(OrdemMissao.etiquetas),
        )
    )

    result = await session.scalars(query)
    ordens = result.all()

    # Transformar para OrdemMissaoList usando from_attributes do Pydantic
    items = [OrdemMissaoList.model_validate(ordem) for ordem in ordens]

    return paginated_response(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    '/route-suggestions',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[RouteSuggestionOut | None],
)
async def get_route_suggestion(
    origem: str,
    dest: str,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
):
    """
    Busca sugestão de rota baseada em missões anteriores (não rascunho).

    Realiza duas buscas:
    1. Rota completa (origem + dest): tvoo_etp, qtd_comb
    2. Apenas destino: alternativa, tvoo_alt

    Isso permite sugerir alternativa mesmo para rotas nunca voadas,
    desde que o destino já tenha sido visitado anteriormente.
    """
    # Validar códigos ICAO
    if len(origem) != ICAO_CODE_LENGTH or len(dest) != ICAO_CODE_LENGTH:
        return success_response(data=None)

    origem_upper = origem.upper()
    dest_upper = dest.upper()

    # Filtro comum: ordens da org ativa, não-rascunho e não-deletadas
    base_filter = [
        OrdemMissao.uae == active_org,
        OrdemMissao.status != 'rascunho',
        OrdemMissao.deleted_at.is_(None),
    ]

    # Query 1: Buscar rota completa (origem + dest) -> tvoo_etp, qtd_comb
    route_result = await session.execute(
        select(
            OrdemEtapa.tvoo_etp,
            OrdemEtapa.qtd_comb,
        )
        .join(OrdemMissao, OrdemEtapa.ordem_id == OrdemMissao.id)
        .where(
            OrdemEtapa.origem == origem_upper,
            OrdemEtapa.dest == dest_upper,
            *base_filter,
        )
        .order_by(OrdemMissao.created_at.desc(), OrdemMissao.id.desc())
        .limit(1)
    )
    route_row = route_result.first()

    # Query 2: Buscar dados do destino (apenas dest) -> alternativa, tvoo_alt
    dest_result = await session.execute(
        select(
            OrdemEtapa.alternativa,
            OrdemEtapa.tvoo_alt,
        )
        .join(OrdemMissao, OrdemEtapa.ordem_id == OrdemMissao.id)
        .where(
            OrdemEtapa.dest == dest_upper,
            *base_filter,
        )
        .order_by(OrdemMissao.created_at.desc(), OrdemMissao.id.desc())
        .limit(1)
    )
    dest_row = dest_result.first()

    # Nenhum dado encontrado
    if not route_row and not dest_row:
        return success_response(data=None)

    # Construir resposta combinada
    return success_response(
        data=RouteSuggestionOut(
            dest=dest_upper,
            # Dados do destino
            alternativa=dest_row.alternativa if dest_row else None,
            tvoo_alt=dest_row.tvoo_alt if dest_row else None,
            # Dados da rota completa
            origem=origem_upper if route_row else None,
            tvoo_etp=route_row.tvoo_etp if route_row else None,
            qtd_comb=route_row.qtd_comb if route_row else None,
            # Flags
            has_route_data=route_row is not None,
            has_destination_data=dest_row is not None,
        )
    )


@router.get(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[OrdemMissaoOut],
)
async def get_ordem(id: int, session: Session, active_org: ActiveOrg):
    """Busca uma ordem de missão por ID"""
    ordem = await session.scalar(
        select(OrdemMissao)
        .where(
            OrdemMissao.id == id,
            OrdemMissao.uae == active_org,
            OrdemMissao.deleted_at.is_(None),
        )
        .options(
            selectinload(OrdemMissao.tripulacao).selectinload(
                OrdemTripulacao.tripulante
            )
        )
    )

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    return success_response(data=ordem)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[OrdemMissaoOut],
)
async def create_ordem(
    ordem_data: OrdemMissaoCreate,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    _: Annotated[User, CreateOM],
):
    """Cria uma nova ordem de missão"""

    # Integridade das etapas x esforço aéreo (regras de negócio no
    # backend; continuidade só é exigida na aprovação)
    validar_integridade_etapas(
        ordem_data.etapas,
        ordem_data.esf_aer,
        exigir_continuidade=False,
    )

    # Calcular data_saida (dia UTC da primeira etapa)
    data_saida = _data_saida_de(ordem_data.etapas)

    # Criar ordem (sempre como rascunho na criação)
    ordem = OrdemMissao(
        numero='auto',  # Regra de negócio: nova ordem é sempre auto
        matricula_anv=ordem_data.matricula_anv,
        tipo=ordem_data.tipo,
        created_by=current_user.id,
        projeto=ordem_data.projeto,
        status='rascunho',  # Regra de negócio: nova ordem é sempre rascunho
        esf_aer=ordem_data.esf_aer,
        campos_especiais=[
            ce.model_dump() for ce in ordem_data.campos_especiais
        ],
        doc_ref=ordem_data.doc_ref,
        data_saida=data_saida,
        uae=active_org,
    )

    session.add(ordem)
    await session.flush()  # Para obter o ID

    # Criar etapas
    for etapa_data in ordem_data.etapas:
        session.add(montar_etapa(ordem.id, etapa_data))

    # Criar tripulação (batch query para evitar N+1)
    tripulacao_criada: list[OrdemTripulacao] = []
    if ordem_data.tripulacao:
        tripulacao_criada = await criar_tripulacao_batch(
            session, ordem.id, ordem_data.tripulacao, uae=active_org
        )

    # Vincular etiquetas (somente da org ativa)
    if ordem_data.etiquetas_ids:
        etiquetas_result = await session.execute(
            select(Etiqueta).where(
                Etiqueta.id.in_(ordem_data.etiquetas_ids),
                Etiqueta.uae == active_org,
            )
        )
        ordem.etiquetas = list(etiquetas_result.scalars().all())

    # Auditoria no mesmo commit da mutação. As etapas saem do payload e a
    # tripulação das linhas devolvidas pelo batch (com `.tripulante` já
    # carregado): as coleções de `ordem` nunca receberam essas linhas.
    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='create',
        resource=RESOURCE,
        resource_id=ordem.id,
        before=None,
        after=ordem_snapshot(
            ordem,
            ordem_data.etapas,
            tripulacao_criada,
            ordem.etiquetas,
        ),
    )

    await session.commit()

    # Recarregar a ordem com todos os relacionamentos (incluindo aninhados)
    ordem_criada = await session.scalar(
        select(OrdemMissao)
        .where(OrdemMissao.id == ordem.id)
        .options(
            selectinload(OrdemMissao.tripulacao).selectinload(
                OrdemTripulacao.tripulante
            )
        )
    )

    return success_response(
        data=OrdemMissaoOut.model_validate(ordem_criada, from_attributes=True),
        message='Ordem de missão criada com sucesso',
    )


@router.put(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[OrdemMissaoOut],
)
async def update_ordem(
    id: int,
    ordem_data: OrdemMissaoUpdate,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    _: Annotated[User, UpdateOM],
):
    """Atualiza uma ordem de missão existente"""
    ordem = await session.scalar(
        select(OrdemMissao).where(
            OrdemMissao.id == id,
            OrdemMissao.uae == active_org,
            OrdemMissao.deleted_at.is_(None),
        )
    )

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    # Impedir edição de ordem cancelada
    if ordem.status == 'cancelada':
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Ordem cancelada não pode ser editada',
        )

    # Transitar status (aprovar/cancelar) exige a permissão granular
    # `ordem_missao.status.update`, separada de `ordem_missao.update`:
    # ops_basico edita campos da OM mas não pode mudar seu status.
    if (
        ordem_data.status is not None
        and ordem_data.status != ordem.status
        and not await has_org_permission(
            current_user,
            session,
            active_org,
            'ops.ordem_missao.status',
            'update',
        )
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Permissão negada: ordem_missao.status.update',
        )

    # Validar mudança de status contra a máquina de estados
    # (bloqueia ex: aprovada -> rascunho)
    if (
        ordem_data.status is not None
        and ordem_data.status != ordem.status
        and ordem_data.status
        not in STATUS_TRANSITIONS.get(ordem.status, set())
    ):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f'Transição de status inválida: '
                f'{ordem.status} -> {ordem_data.status}'
            ),
        )

    # Snapshot anterior antes da 1ª mutação: sai do objeto já carregado
    # (etapas/tripulação/etiquetas vêm por lazy='selectin', assim como o
    # `tripulante` e seu `user`), sem select novo.
    before_snapshot = ordem_snapshot(
        ordem, ordem.etapas, ordem.tripulacao, ordem.etiquetas
    )

    if ordem_data.status == 'cancelada':
        # Cancelamento: atualizar apenas o status
        ordem.status = 'cancelada'

        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE,
            resource_id=ordem.id,
            before=before_snapshot,
            after=ordem_snapshot(
                ordem, ordem.etapas, ordem.tripulacao, ordem.etiquetas
            ),
        )

        await session.commit()

        ordem_atualizada = await session.scalar(
            select(OrdemMissao)
            .where(OrdemMissao.id == id)
            .options(
                selectinload(OrdemMissao.tripulacao).selectinload(
                    OrdemTripulacao.tripulante
                )
            )
        )

        return success_response(
            data=OrdemMissaoOut.model_validate(
                ordem_atualizada, from_attributes=True
            ),
            message='Ordem de missão cancelada com sucesso',
        )

    # Integridade: valida as etapas resultantes (payload ou as já
    # persistidas) contra o esforço aéreo resultante; a continuidade da
    # rota é exigida quando a ordem resulta aprovada
    etapas_alvo = (
        ordem_data.etapas if ordem_data.etapas is not None else ordem.etapas
    )
    esf_aer_alvo = (
        ordem_data.esf_aer if ordem_data.esf_aer is not None else ordem.esf_aer
    )
    status_final = ordem_data.status or ordem.status
    validar_integridade_etapas(
        etapas_alvo,
        esf_aer_alvo,
        exigir_continuidade=status_final == 'aprovada',
    )

    # Identificar transição para aprovada para gerar número
    if (
        ordem_data.status == 'aprovada'
        and ordem.status == 'rascunho'
        and (ordem.numero == 'auto' or not ordem.numero)
    ):
        # Garantir que temos a data_saida
        ordem.data_saida = _data_saida_de(ordem_data.etapas or ordem.etapas)

        if not ordem.data_saida:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='A ordem deve ter pelo menos uma etapa',
            )

        # A numeração (advisory lock + MAX+1) e a checagem de unicidade
        # vivem no serviço. `data_saida` acabou de ser derivada das
        # etapas, então o ano dela é o mesmo das etapas do payload.
        ordem.numero = await emitir_numero_om(
            session,
            uae=ordem.uae,
            ano=ordem.data_saida.year,
            excluir_id=id,
        )

    # Atualizar campos simples
    update_data = ordem_data.model_dump(exclude_unset=True)

    # As chaves das coleções são consumidas (del) mais abaixo; guardar
    # aqui quais delas o PUT trouxe, para o snapshot posterior saber se
    # lê o payload/o retorno do batch (linhas recém-criadas, ausentes das
    # coleções do `ordem`) ou as coleções originais já carregadas.
    etapas_no_payload = 'etapas' in update_data
    tripulacao_no_payload = 'tripulacao' in update_data
    tripulacao_atualizada: list[OrdemTripulacao] = []

    # Se um número foi gerado automaticamente, remover 'numero' de update_data
    # para evitar sobrescrever o valor gerado
    if (
        ordem_data.status == 'aprovada'
        and ordem.status == 'rascunho'
        and ordem.numero != 'auto'  # Número foi gerado (linha 453)
        and 'numero' in update_data
    ):
        del update_data['numero']

    # Validação de edição manual de número (somente para ordens aprovadas)
    if ordem_data.numero and ordem_data.numero not in {'auto', ordem.numero}:
        # Só permite editar número em ordens aprovadas
        # (em rascunho, o número é gerado automaticamente na aprovação)
        status_atual = ordem_data.status or ordem.status
        if status_atual != 'aprovada':
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'O número da OM só pode ser editado '
                    'após a ordem ser aprovada'
                ),
            )

        # Validar unicidade do novo número (ano + UAE). `uae` é NOT NULL
        # no model, então só o ano pode faltar aqui.
        target_year = None
        if ordem_data.etapas:
            target_year = (
                min(e.dt_dep for e in ordem_data.etapas)
                .astimezone(timezone.utc)
                .year
            )
        elif ordem.data_saida:
            target_year = ordem.data_saida.year

        if target_year:
            await assert_numero_om_livre(
                session,
                numero=ordem_data.numero,
                uae=ordem.uae,
                ano=target_year,
                excluir_id=id,
                rotulo=ordem_data.numero,
            )

    # Tratar campos especiais
    if 'campos_especiais' in update_data:
        ordem.campos_especiais = (
            [ce.model_dump() for ce in ordem_data.campos_especiais]
            if ordem_data.campos_especiais
            else []
        )
        del update_data['campos_especiais']

    # Atualizar etapas se fornecidas
    if 'etapas' in update_data:
        # Atualizar data_saida
        ordem.data_saida = _data_saida_de(ordem_data.etapas)

        # Remover etapas existentes
        for etapa in ordem.etapas:
            await session.delete(etapa)

        # Criar novas etapas
        for etapa_data in ordem_data.etapas or []:
            session.add(montar_etapa(ordem.id, etapa_data))

        del update_data['etapas']

    # Atualizar tripulação se fornecida (batch query para evitar N+1)
    if 'tripulacao' in update_data:
        # O p_g da linha é snapshot do posto na criação da OM. Como a
        # atualização apaga e recria a tripulação, guarde o valor já
        # gravado ANTES do delete: quem permanece na mesma função
        # mantém o posto de origem e só quem entra agora é carimbado
        # com o posto atual. Sem isso, editar a data de uma OM antiga
        # recarimbaria a tripulação inteira com os postos de hoje.
        p_g_preservado = {
            (trip.tripulante_id, trip.funcao): trip.p_g
            for trip in ordem.tripulacao
        }

        # Remover tripulação existente
        for trip in ordem.tripulacao:
            await session.delete(trip)

        # Criar nova tripulação
        if ordem_data.tripulacao:
            tripulacao_atualizada = await criar_tripulacao_batch(
                session,
                ordem.id,
                ordem_data.tripulacao,
                uae=active_org,
                p_g_preservado=p_g_preservado,
            )

        del update_data['tripulacao']

    # Atualizar etiquetas se fornecidas (somente da org ativa)
    if 'etiquetas_ids' in update_data:
        if ordem_data.etiquetas_ids is not None:
            etiquetas_result = await session.execute(
                select(Etiqueta).where(
                    Etiqueta.id.in_(ordem_data.etiquetas_ids),
                    Etiqueta.uae == active_org,
                )
            )
            ordem.etiquetas = list(etiquetas_result.scalars().all())
        else:
            ordem.etiquetas = []
        del update_data['etiquetas_ids']

    # Atualizar demais campos
    for key, value in update_data.items():
        if value is not None:
            setattr(ordem, key, value)

    # Auditoria: quando a chave veio no PUT, o snapshot posterior lê o
    # payload/o retorno do batch; senão, as coleções originais do `ordem`.
    etapas_log = (
        (ordem_data.etapas or []) if etapas_no_payload else ordem.etapas
    )
    tripulacao_log = (
        tripulacao_atualizada if tripulacao_no_payload else ordem.tripulacao
    )
    after_snapshot = ordem_snapshot(
        ordem, etapas_log, tripulacao_log, ordem.etiquetas
    )
    if before_snapshot != after_snapshot:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE,
            resource_id=ordem.id,
            before=before_snapshot,
            after=after_snapshot,
        )

    await session.commit()

    # Recarregar a ordem com todos os relacionamentos (incluindo aninhados)
    ordem_atualizada = await session.scalar(
        select(OrdemMissao)
        .where(OrdemMissao.id == id)
        .options(
            selectinload(OrdemMissao.tripulacao).selectinload(
                OrdemTripulacao.tripulante
            )
        )
    )

    return success_response(
        data=OrdemMissaoOut.model_validate(
            ordem_atualizada, from_attributes=True
        ),
        message='Ordem de missão atualizada com sucesso',
    )


@router.delete(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_ordem(
    id: int,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    _: Annotated[User, DeleteOM],
):
    """Soft delete de uma ordem de missão"""
    ordem = await session.scalar(
        select(OrdemMissao).where(
            OrdemMissao.id == id,
            OrdemMissao.uae == active_org,
            OrdemMissao.deleted_at.is_(None),
        )
    )

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    # Apenas rascunhos podem ser excluídos: OM aprovada é cancelada, não
    # excluída — o número emitido permanece reservado (a numeração via
    # MAX ignora deletadas, então excluir uma aprovada liberaria reuso)
    if ordem.status != 'rascunho':
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                'Apenas rascunhos podem ser excluídos. '
                'Para uma OM aprovada, use o cancelamento.'
            ),
        )

    # Snapshot rico antes do soft delete (etapas/tripulação/etiquetas já
    # vêm carregadas por lazy='selectin')
    before_snapshot = ordem_snapshot(
        ordem, ordem.etapas, ordem.tripulacao, ordem.etiquetas
    )

    ordem.deleted_at = datetime.now(timezone.utc)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='delete',
        resource=RESOURCE,
        resource_id=id,
        before=before_snapshot,
        after=None,
    )

    await session.commit()

    return success_response(message='Ordem de missão excluída com sucesso')
