"""Router do módulo Operações / Manobras / Exercícios."""

from collections import defaultdict
from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, distinct, or_
from sqlalchemy import func as sql_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TripEtapa,
)
from fcontrol_api.models.shared.aeronaves import Aeronave, ProjetoAnv
from fcontrol_api.models.shared.operacao import (
    Operacao,
    OperacaoEtapa,
    OperacaoPessoal,
)
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.ops.operacao import (
    AssociarEtapas,
    AssociarResult,
    CidadeMini,
    EsforcoBloco,
    EsforcoRow,
    EtapaCandidata,
    OperacaoCreate,
    OperacaoDetail,
    OperacaoEtapaRow,
    OperacaoKpis,
    OperacaoListItem,
    OperacaoListResponse,
    OperacaoPessoalIn,
    OperacaoPessoalOut,
    OperacaoTabCounts,
    OperacaoUpdate,
    SeboRow,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/operacoes', tags=['operacoes'])

ViewOper = Depends(permission_checker('operacoes', 'view'))
# Todas as escritas do módulo (criar/editar/associar/pessoal) exigem
# `operacoes.create`, espelhando o gating do frontend (PermBased).
CreateOper = Depends(permission_checker('operacoes', 'create'))
DeleteOper = Depends(permission_checker('operacoes', 'delete'))


def _dias(inicio, fim) -> int:
    return (fim - inicio).days + 1


def _etapa_ids_subq(op_id: int):
    """Subquery com os ids de etapa vinculados à operação."""
    return (
        select(OperacaoEtapa.etapa_id)
        .where(OperacaoEtapa.operacao_id == op_id)
        .scalar_subquery()
    )


async def _get_op(
    session: AsyncSession, op_id: int, active_org: str
) -> Operacao:
    op = await session.scalar(
        select(Operacao).where(
            Operacao.id == op_id,
            Operacao.uae == active_org,
        )
    )
    if not op:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Operação não encontrada',
        )
    return op


def _erro_operacao(exc: IntegrityError) -> HTTPException:
    """Mapeia a violação de constraint para uma resposta legível."""
    msg = str(exc.orig)
    if 'uq_operacao_uae_nome' in msg:
        return HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe uma operação com esse nome nesta unidade',
        )
    if 'cidade_id' in msg:
        return HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Cidade inválida',
        )
    return HTTPException(
        status_code=HTTPStatus.CONFLICT,
        detail='Conflito ao salvar a operação; tente novamente',
    )


def _list_item(
    op: Operacao, horas: int, etapas: int, anv: int
) -> OperacaoListItem:
    return OperacaoListItem(
        id=op.id,
        numero=op.numero,
        nome=op.nome,
        tipo=op.tipo,
        status=op.status,
        documento_referencia=op.documento_referencia,
        cidade=CidadeMini.model_validate(op.cidade) if op.cidade else None,
        data_inicio=op.data_inicio,
        data_fim=op.data_fim,
        dias=_dias(op.data_inicio, op.data_fim),
        horas=horas,
        etapas=etapas,
        anv=anv,
    )


def _pessoal_out(p: OperacaoPessoal) -> OperacaoPessoalOut:
    return OperacaoPessoalOut(
        id=p.id,
        user=UserPublic.model_validate(p.user),
        func=p.func,
        sit=p.sit,
        data_ingresso=p.data_ingresso,
        data_regresso=p.data_regresso,
        dias=_dias(p.data_ingresso, p.data_regresso),
    )


# --------------------------------------------------------------------------- #
# Lista
# --------------------------------------------------------------------------- #
@router.get(
    '/',
    response_model=ApiResponse[OperacaoListResponse],
    dependencies=[ViewOper],
)
async def list_operacoes(
    session: Session,
    active_org: ActiveOrg,
    status: Annotated[str | None, Query()] = None,
    tipo: Annotated[str | None, Query()] = None,
    date_start: Annotated[date | None, Query()] = None,
    date_end: Annotated[date | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
):
    base = Operacao.uae == active_org

    # Contadores por status (independentes dos filtros de status)
    counts_rows = await session.execute(
        select(Operacao.status, sql_func.count())
        .where(base)
        .group_by(Operacao.status)
    )
    by_status = {s: c for s, c in counts_rows.all()}
    counts = OperacaoTabCounts(
        todas=sum(by_status.values()),
        andamento=by_status.get('andamento', 0),
        encerrada=by_status.get('encerrada', 0),
        planejada=by_status.get('planejada', 0),
        cancelada=by_status.get('cancelada', 0),
    )

    query = select(Operacao).where(base)
    if status:
        query = query.where(Operacao.status == status)
    if tipo:
        query = query.where(Operacao.tipo == tipo)
    if date_start:
        query = query.where(Operacao.data_fim >= date_start)
    if date_end:
        query = query.where(Operacao.data_inicio <= date_end)
    if q:
        like = f'%{q}%'
        query = query.where(
            or_(
                Operacao.nome.ilike(like),
                Operacao.documento_referencia.ilike(like),
            )
        )
    query = query.order_by(Operacao.data_inicio.desc(), Operacao.id.desc())

    ops = (await session.scalars(query)).unique().all()

    op_ids = [o.id for o in ops]
    agg: dict[int, tuple[int, int, int]] = {}
    if op_ids:
        agg_rows = await session.execute(
            select(
                OperacaoEtapa.operacao_id,
                sql_func.coalesce(sql_func.sum(Etapa.tvoo), 0),
                sql_func.count(Etapa.id),
                sql_func.count(distinct(Etapa.anv)),
            )
            .join(Etapa, Etapa.id == OperacaoEtapa.etapa_id)
            .where(OperacaoEtapa.operacao_id.in_(op_ids))
            .group_by(OperacaoEtapa.operacao_id)
        )
        agg = {r[0]: (r[1], r[2], r[3]) for r in agg_rows.all()}

    items = [_list_item(o, *agg.get(o.id, (0, 0, 0))) for o in ops]

    return success_response(
        data=OperacaoListResponse(items=items, counts=counts)
    )


# --------------------------------------------------------------------------- #
# Criar
# --------------------------------------------------------------------------- #
@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[OperacaoListItem],
)
async def create_operacao(
    payload: OperacaoCreate,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    # `numero` é max+1 por org: creates concorrentes podem colidir no
    # uq_operacao_uae_numero — nesse caso recalcula e tenta de novo.
    tentativas = 3
    for tentativa in range(tentativas):
        max_num = await session.scalar(
            select(sql_func.max(Operacao.numero)).where(
                Operacao.uae == active_org
            )
        )
        op = Operacao(
            numero=(max_num or 0) + 1,
            nome=payload.nome,
            tipo=payload.tipo,
            cidade_id=payload.cidade_id,
            data_inicio=payload.data_inicio,
            data_fim=payload.data_fim,
            status=payload.status,
            uae=active_org,
            created_by=user.id,
            documento_referencia=payload.documento_referencia,
            obs=payload.obs,
        )
        session.add(op)
        try:
            await session.commit()
            break
        except IntegrityError as exc:
            await session.rollback()
            colidiu_numero = 'uq_operacao_uae_numero' in str(exc.orig)
            if colidiu_numero and tentativa < tentativas - 1:
                continue
            raise _erro_operacao(exc) from exc

    await session.refresh(op)
    await log_user_action(
        session=session,
        user_id=user.id,
        action='create',
        resource='operacoes',
        resource_id=op.id,
    )
    await session.commit()

    return success_response(
        data=_list_item(op, 0, 0, 0),
        message='Operação criada com sucesso',
    )


# --------------------------------------------------------------------------- #
# Detalhe (KPIs + esforço + pau de sebo)
# --------------------------------------------------------------------------- #
@router.get(
    '/{op_id}',
    response_model=ApiResponse[OperacaoDetail],
    dependencies=[ViewOper],
)
async def get_operacao(op_id: int, session: Session, active_org: ActiveOrg):
    op = await _get_op(session, op_id, active_org)
    etapa_ids = _etapa_ids_subq(op.id)
    in_op = Etapa.id.in_(etapa_ids)

    kpi = (
        await session.execute(
            select(
                sql_func.coalesce(sql_func.sum(Etapa.tvoo), 0),
                sql_func.count(Etapa.id),
                sql_func.count(distinct(Etapa.anv)),
                sql_func.coalesce(sql_func.sum(Etapa.pax), 0),
                sql_func.coalesce(sql_func.sum(Etapa.carga), 0),
                sql_func.coalesce(sql_func.sum(Etapa.comb), 0),
                sql_func.count(distinct(Etapa.missao_id)),
            ).where(in_op)
        )
    ).one()

    modelos = (
        await session.scalar(
            select(sql_func.count(distinct(ProjetoAnv.modelo)))
            .select_from(Etapa)
            .join(Aeronave, Aeronave.matricula == Etapa.anv)
            .join(ProjetoAnv, ProjetoAnv.id_projeto == Aeronave.projeto)
            .where(in_op)
        )
    ) or 0

    kpis = OperacaoKpis(
        horas=kpi[0],
        etapas=kpi[1],
        anv=kpi[2],
        pax=kpi[3],
        carga=kpi[4],
        comb=kpi[5],
        missoes=kpi[6],
        modelos=modelos,
    )

    # Esforço aéreo
    esf_rows = await session.execute(
        select(
            OIEtapa.esf_aer_id,
            EsforcoAereo.descricao,
            sql_func.count(distinct(OIEtapa.etapa_id)),
            sql_func.coalesce(sql_func.sum(OIEtapa.tvoo), 0),
        )
        .join(EsforcoAereo, EsforcoAereo.id == OIEtapa.esf_aer_id)
        .where(OIEtapa.etapa_id.in_(etapa_ids))
        .group_by(OIEtapa.esf_aer_id, EsforcoAereo.descricao)
        .order_by(sql_func.sum(OIEtapa.tvoo).desc())
    )
    esforco_rows = [
        EsforcoRow(esf_aer_id=r[0], descricao=r[1], etapas=r[2], horas=r[3])
        for r in esf_rows.all()
    ]
    esforco = EsforcoBloco(
        rows=esforco_rows,
        total_etapas=sum(r.etapas for r in esforco_rows),
        total_horas=sum(r.horas for r in esforco_rows),
    )

    # Pau de sebo (por tripulante, função predominante)
    sebo_rows = await session.execute(
        select(
            TripEtapa.trip_id,
            TripEtapa.func,
            User.p_g,
            User.nome_guerra,
            sql_func.coalesce(sql_func.sum(Etapa.tvoo), 0),
            sql_func.count(distinct(Etapa.id)),
        )
        .join(Etapa, Etapa.id == TripEtapa.etapa_id)
        .join(Tripulante, Tripulante.id == TripEtapa.trip_id)
        .join(User, User.id == Tripulante.user_id)
        .where(in_op)
        .group_by(
            TripEtapa.trip_id,
            TripEtapa.func,
            User.p_g,
            User.nome_guerra,
        )
    )
    by_trip: dict[int, dict] = {}
    for trip_id, func, p_g, ng, horas_t, et_t in sebo_rows.all():
        d = by_trip.setdefault(
            trip_id,
            {'nome': f'{p_g} {ng}', 'horas': 0, 'etapas': 0, 'funcs': {}},
        )
        d['horas'] += horas_t
        d['etapas'] += et_t
        d['funcs'][func] = d['funcs'].get(func, 0) + et_t

    sebo = [
        SeboRow(
            trip_id=trip_id,
            nome=d['nome'],
            func=max(d['funcs'], key=d['funcs'].get),
            etapas=d['etapas'],
            horas=d['horas'],
        )
        for trip_id, d in by_trip.items()
    ]
    sebo.sort(key=lambda s: s.horas, reverse=True)

    detail = OperacaoDetail(
        id=op.id,
        numero=op.numero,
        nome=op.nome,
        tipo=op.tipo,
        status=op.status,
        documento_referencia=op.documento_referencia,
        cidade=CidadeMini.model_validate(op.cidade) if op.cidade else None,
        data_inicio=op.data_inicio,
        data_fim=op.data_fim,
        dias=_dias(op.data_inicio, op.data_fim),
        obs=op.obs,
        created_at=op.created_at,
        kpis=kpis,
        esforco=esforco,
        sebo=sebo,
    )
    return success_response(data=detail)


# --------------------------------------------------------------------------- #
# Editar / excluir
# --------------------------------------------------------------------------- #
@router.put('/{op_id}', response_model=ApiResponse[None])
async def update_operacao(
    op_id: int,
    payload: OperacaoUpdate,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    op = await _get_op(session, op_id, active_org)
    changes = payload.model_dump(exclude_unset=True)

    nova_ini = changes.get('data_inicio', op.data_inicio)
    nova_fim = changes.get('data_fim', op.data_fim)
    if nova_fim < nova_ini:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='data_fim deve ser maior ou igual a data_inicio',
        )
    # Encurtar o período não pode deixar etapa associada fora dele
    # (mesmo contrato imposto nas candidatas e no associar).
    if (nova_ini, nova_fim) != (op.data_inicio, op.data_fim):
        fora = await session.scalar(
            select(sql_func.count())
            .select_from(Etapa)
            .where(
                Etapa.id.in_(_etapa_ids_subq(op.id)),
                ~Etapa.data.between(nova_ini, nova_fim),
            )
        )
        if fora:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    f'{fora} etapa(s) associada(s) ficariam fora do novo '
                    'período; desassocie-as antes de alterar as datas'
                ),
            )

    before: dict = {}
    after: dict = {}
    for key, value in changes.items():
        old = getattr(op, key)
        if old != value:
            before[key] = str(old) if hasattr(old, 'isoformat') else old
            after[key] = str(value) if hasattr(value, 'isoformat') else value
            setattr(op, key, value)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _erro_operacao(exc) from exc

    await log_user_action(
        session=session,
        user_id=user.id,
        action='patch',
        resource='operacoes',
        resource_id=op.id,
        before=before,
        after=after,
    )
    await session.commit()
    return success_response(message='Operação atualizada')


@router.delete('/{op_id}', response_model=ApiResponse[None])
async def delete_operacao(
    op_id: int,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, DeleteOper],
):
    op = await _get_op(session, op_id, active_org)
    # Hard delete: o ON DELETE CASCADE remove vínculos de etapa e o
    # pessoal; os registros de voo (etapas) são preservados.
    await session.delete(op)
    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='operacoes',
        resource_id=op.id,
    )
    await session.commit()
    return success_response(message='Operação excluída')


# --------------------------------------------------------------------------- #
# Etapas associadas
# --------------------------------------------------------------------------- #
@router.get(
    '/{op_id}/etapas',
    response_model=ApiResponse[list[OperacaoEtapaRow]],
    dependencies=[ViewOper],
)
async def list_etapas(op_id: int, session: Session, active_org: ActiveOrg):
    op = await _get_op(session, op_id, active_org)
    etapas = (
        await session.scalars(
            select(Etapa)
            .join(OperacaoEtapa, OperacaoEtapa.etapa_id == Etapa.id)
            .where(OperacaoEtapa.operacao_id == op.id)
            .order_by(Etapa.data, Etapa.id)
        )
    ).all()
    if not etapas:
        return success_response(data=[])

    ids = [e.id for e in etapas]

    esf_map: dict[int, list[str]] = defaultdict(list)
    esf_rows = await session.execute(
        select(OIEtapa.etapa_id, EsforcoAereo.descricao)
        .join(EsforcoAereo, EsforcoAereo.id == OIEtapa.esf_aer_id)
        .where(OIEtapa.etapa_id.in_(ids))
    )
    for etapa_id, desc in esf_rows.all():
        esf_map[etapa_id].append(desc)

    rows = [
        OperacaoEtapaRow(
            id=e.id,
            data=e.data,
            origem=e.origem,
            destino=e.destino,
            anv=e.anv,
            esforco=', '.join(esf_map.get(e.id, [])) or None,
            tvoo=e.tvoo,
            dep=e.dep,
            arr=e.arr,
        )
        for e in etapas
    ]
    return success_response(data=rows)


@router.get(
    '/{op_id}/candidatas',
    response_model=ApiResponse[list[EtapaCandidata]],
    dependencies=[ViewOper],
)
async def list_candidatas(op_id: int, session: Session, active_org: ActiveOrg):
    op = await _get_op(session, op_id, active_org)
    # Só etapas de missões da org ativa (escopo via missão, já que
    # Etapa não tem `uae` próprio): evita listar voos de outra unidade.
    rows = await session.execute(
        select(Etapa, OperacaoEtapa.operacao_id)
        .join(Missao, Missao.id == Etapa.missao_id)
        .outerjoin(OperacaoEtapa, OperacaoEtapa.etapa_id == Etapa.id)
        .where(
            Missao.uae == active_org,
            Etapa.data.between(op.data_inicio, op.data_fim),
            or_(
                OperacaoEtapa.operacao_id.is_(None),
                OperacaoEtapa.operacao_id != op.id,
            ),
        )
        .order_by(Etapa.data, Etapa.id)
    )

    cands = [
        EtapaCandidata(
            id=e.id,
            data=e.data,
            origem=e.origem,
            destino=e.destino,
            anv=e.anv,
            missao_id=e.missao_id,
            tvoo=e.tvoo,
            dep=e.dep,
            arr=e.arr,
            bloqueada=cur_op is not None,
            operacao_atual=cur_op,
        )
        for e, cur_op in rows.all()
    ]
    return success_response(data=cands)


@router.post('/{op_id}/etapas', response_model=ApiResponse[AssociarResult])
async def associar_etapas(
    op_id: int,
    payload: AssociarEtapas,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    op = await _get_op(session, op_id, active_org)

    # Apenas etapas existentes, de missões da org ativa (bloqueia voos
    # de outra unidade — escopo herdado da missão) e dentro do período
    # da operação (mesmo contrato das candidatas).
    validos = set(
        (
            await session.scalars(
                select(Etapa.id)
                .join(Missao, Missao.id == Etapa.missao_id)
                .where(
                    Etapa.id.in_(payload.etapa_ids),
                    Missao.uae == active_org,
                    Etapa.data.between(op.data_inicio, op.data_fim),
                )
            )
        ).all()
    )
    # Vínculos já existentes (1:N — etapa_id é PK em operacao_etapa)
    existentes = {
        row.etapa_id: row.operacao_id
        for row in (
            await session.scalars(
                select(OperacaoEtapa).where(
                    OperacaoEtapa.etapa_id.in_(payload.etapa_ids)
                )
            )
        ).all()
    }

    associadas = 0
    bloqueadas: list[int] = []
    for eid in payload.etapa_ids:
        if eid not in validos:
            continue
        atual = existentes.get(eid)
        if atual == op.id:
            continue
        if atual is not None:
            bloqueadas.append(eid)
            continue
        session.add(OperacaoEtapa(etapa_id=eid, operacao_id=op.id))
        associadas += 1

    await log_user_action(
        session=session,
        user_id=user.id,
        action='patch',
        resource='operacoes',
        resource_id=op.id,
        after={'associadas': associadas, 'bloqueadas': bloqueadas},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        # Corrida: outra requisição associou a mesma etapa entre o
        # check e o INSERT (a PK etapa_id garante a consistência).
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Alguma etapa acabou de ser associada a outra operação; '
                'recarregue a lista e tente novamente'
            ),
        ) from exc
    return success_response(
        data=AssociarResult(associadas=associadas, bloqueadas=bloqueadas),
        message=f'{associadas} etapa(s) associada(s)',
    )


@router.delete('/{op_id}/etapas/{etapa_id}', response_model=ApiResponse[None])
async def desassociar_etapa(
    op_id: int,
    etapa_id: int,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    op = await _get_op(session, op_id, active_org)
    result = await session.execute(
        delete(OperacaoEtapa).where(
            OperacaoEtapa.etapa_id == etapa_id,
            OperacaoEtapa.operacao_id == op.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etapa não associada a esta operação',
        )
    await log_user_action(
        session=session,
        user_id=user.id,
        action='patch',
        resource='operacoes',
        resource_id=op.id,
        before={'etapa_desassociada': etapa_id},
    )
    await session.commit()
    return success_response(message='Etapa desassociada')


# --------------------------------------------------------------------------- #
# Pessoal envolvido
# --------------------------------------------------------------------------- #
@router.get(
    '/{op_id}/pessoal',
    response_model=ApiResponse[list[OperacaoPessoalOut]],
    dependencies=[ViewOper],
)
async def list_pessoal(op_id: int, session: Session, active_org: ActiveOrg):
    op = await _get_op(session, op_id, active_org)
    pessoal = (
        await session.scalars(
            select(OperacaoPessoal)
            .where(OperacaoPessoal.operacao_id == op.id)
            .order_by(OperacaoPessoal.data_ingresso, OperacaoPessoal.id)
        )
    ).all()
    return success_response(data=[_pessoal_out(p) for p in pessoal])


def _erro_pessoal(exc: IntegrityError) -> HTTPException:
    msg = str(exc.orig)
    if 'uq_operacao_pessoal_user' in msg:
        return HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Militar já associado a esta operação',
        )
    if 'user_id' in msg:
        return HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Usuário inválido',
        )
    return HTTPException(
        status_code=HTTPStatus.CONFLICT,
        detail='Conflito ao salvar o militar; tente novamente',
    )


@router.post(
    '/{op_id}/pessoal',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[OperacaoPessoalOut],
)
async def add_pessoal(
    op_id: int,
    payload: OperacaoPessoalIn,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    op = await _get_op(session, op_id, active_org)
    pessoa = OperacaoPessoal(
        operacao_id=op.id,
        user_id=payload.user_id,
        func=payload.func,
        sit=payload.sit,
        data_ingresso=payload.data_ingresso,
        data_regresso=payload.data_regresso,
    )
    session.add(pessoa)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _erro_pessoal(exc) from exc
    await session.refresh(pessoa, ['user'])
    await log_user_action(
        session=session,
        user_id=user.id,
        action='create',
        resource='operacoes',
        resource_id=op.id,
        after={'pessoal_add': payload.user_id},
    )
    await session.commit()
    return success_response(
        data=_pessoal_out(pessoa), message='Pessoa adicionada'
    )


@router.put('/{op_id}/pessoal/{pessoal_id}', response_model=ApiResponse[None])
async def update_pessoal(
    op_id: int,
    pessoal_id: int,
    payload: OperacaoPessoalIn,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    op = await _get_op(session, op_id, active_org)
    pessoa = await session.scalar(
        select(OperacaoPessoal).where(
            OperacaoPessoal.id == pessoal_id,
            OperacaoPessoal.operacao_id == op.id,
        )
    )
    if not pessoa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Pessoa não encontrada nesta operação',
        )
    pessoa.user_id = payload.user_id
    pessoa.func = payload.func
    pessoa.sit = payload.sit
    pessoa.data_ingresso = payload.data_ingresso
    pessoa.data_regresso = payload.data_regresso
    await log_user_action(
        session=session,
        user_id=user.id,
        action='patch',
        resource='operacoes',
        resource_id=op.id,
        after={'pessoal_update': pessoal_id},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _erro_pessoal(exc) from exc
    return success_response(message='Pessoa atualizada')


@router.delete(
    '/{op_id}/pessoal/{pessoal_id}', response_model=ApiResponse[None]
)
async def remove_pessoal(
    op_id: int,
    pessoal_id: int,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, CreateOper],
):
    op = await _get_op(session, op_id, active_org)
    pessoa = await session.scalar(
        select(OperacaoPessoal).where(
            OperacaoPessoal.id == pessoal_id,
            OperacaoPessoal.operacao_id == op.id,
        )
    )
    if not pessoa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Pessoa não encontrada nesta operação',
        )
    await session.delete(pessoa)
    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='operacoes',
        resource_id=op.id,
        before={'pessoal_remove': pessoal_id},
    )
    await session.commit()
    return success_response(message='Pessoa removida')
