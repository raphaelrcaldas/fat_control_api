from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.aeronaves import ProjetoAnv, TenantProjeto
from fcontrol_api.models.shared.funcoes import FuncaoUae
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.ops.tripulantes import (
    BaseTrip,
    TripCreate,
    TripSchema,
    TripUpdate,
    TripWithFunc,
)
from fcontrol_api.schemas.response import ApiPaginatedResponse, ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import paginated_response, success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=ApiResponse[TripSchema]
)
async def create_trip(
    trip: TripCreate,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, Depends(permission_checker('trips', 'create'))],
):
    db_trig = await session.scalar(
        select(Tripulante).where(
            (Tripulante.trig == trip.trig) & (Tripulante.uae == active_org)
        )
    )

    if db_trig:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Trigrama já registrado',
        )

    db_trip = await session.scalar(
        select(Tripulante).where(
            (Tripulante.user_id == trip.user_id)
            & (Tripulante.uae == active_org)
        )
    )

    if db_trip:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Tripulante já registrado',
        )

    # `tripulantes.func` é FK para `funcoes.cod`, mas o conjunto válido é o
    # que a unidade opera (funcoes_uae) — mesmo racional do `proj`.
    func_autorizada = await session.scalar(
        select(FuncaoUae.id).where(
            FuncaoUae.uae == active_org,
            FuncaoUae.func_cod == trip.func,
            FuncaoUae.active.is_(True),
        )
    )
    if not func_autorizada:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Função não operada pela organização',
        )

    # `tripulantes.proj` é FK para `projetos_anvs.modelo` e a org só opera
    # os projetos associados em tenant_projetos.
    proj_autorizado = await session.scalar(
        select(ProjetoAnv.modelo)
        .join(TenantProjeto, TenantProjeto.projeto == ProjetoAnv.id_projeto)
        .where(
            TenantProjeto.uae == active_org,
            ProjetoAnv.modelo == trip.proj,
        )
    )
    if not proj_autorizado:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Projeto não disponível para a organização',
        )

    tripulante = Tripulante(
        user_id=trip.user_id,
        trig=trip.trig,
        active=trip.active,
        uae=active_org,
        func=trip.func,
        oper=trip.oper,
        proj=trip.proj,
        data_op=trip.data_op,
    )

    session.add(tripulante)
    await session.flush()

    await log_user_action(
        session=session,
        user_id=user.id,
        action='create',
        resource='trips',
        resource_id=tripulante.id,
        after={
            'user_id': tripulante.user_id,
            'trig': tripulante.trig,
            'active': tripulante.active,
            'func': tripulante.func,
            'oper': tripulante.oper,
            'proj': tripulante.proj,
            'data_op': (
                tripulante.data_op.isoformat() if tripulante.data_op else None
            ),
        },
    )

    await session.commit()
    await session.refresh(tripulante)

    return success_response(
        data=TripSchema.model_validate(tripulante),
        message='Tripulante adicionado com sucesso',
    )


@router.get(
    '/me', status_code=HTTPStatus.OK, response_model=ApiResponse[TripWithFunc]
)
async def get_my_trip(
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
):
    """
    Retorna o tripulante do usuário autenticado.
    """
    trip = await session.scalar(
        select(Tripulante).where(
            Tripulante.user_id == current_user.id,
            Tripulante.uae == active_org,
        )
    )

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado para este usuário',
        )

    return success_response(data=TripWithFunc.model_validate(trip))


@router.get(
    '/user-ids',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[int]],
)
async def get_trip_user_ids(session: Session, active_org: ActiveOrg):
    """Retorna os user_ids de todos os tripulantes da UAE."""
    result = await session.scalars(
        select(Tripulante.user_id).where(Tripulante.uae == active_org)
    )
    return success_response(data=list(result.all()))


@router.get(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[TripWithFunc],
)
async def get_trip(
    id: int,
    session: Session,
    active_org: ActiveOrg,
):
    trip = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == id, Tripulante.uae == active_org
        )
    )

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado',
        )

    return success_response(data=TripWithFunc.model_validate(trip))


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiPaginatedResponse[TripWithFunc],
)
async def list_trips(
    session: Session,
    active_org: ActiveOrg,
    active: bool = True,
    page: int = 1,
    per_page: int = 10,
    search: str | None = None,
    p_g: str | None = None,
    func: str | None = None,
    oper: str | None = None,
):
    # Query base para filtrar IDs
    filter_query = (
        select(Tripulante.id)
        .join(User)
        .join(PostoGrad)
        .where(
            User.active,
            Tripulante.active == active,
            Tripulante.uae == active_org,
        )
    )

    # Filtro de busca por nome/trigrama
    if search:
        search_term = search.lower()
        filter_query = filter_query.where(
            sql_func.unaccent(Tripulante.trig).ilike(
                sql_func.unaccent(f'%{search_term}%')
            )
            | sql_func.unaccent(User.nome_guerra).ilike(
                sql_func.unaccent(f'%{search_term}%')
            )
            | sql_func.unaccent(User.nome_completo).ilike(
                sql_func.unaccent(f'%{search_term}%')
            )
        )

    # Filtro por posto/graduação
    if p_g:
        p_g_list = [pg.strip() for pg in p_g.split(',') if pg.strip()]
        if p_g_list:
            filter_query = filter_query.where(User.p_g.in_(p_g_list))

    # Filtro por função (coluna direta em tripulantes)
    if func:
        func_list = [f.strip() for f in func.split(',') if f.strip()]
        if func_list:
            filter_query = filter_query.where(Tripulante.func.in_(func_list))

    # Filtro por operacionalidade (coluna direta em tripulantes)
    if oper:
        oper_list = [o.strip() for o in oper.split(',') if o.strip()]
        if oper_list:
            filter_query = filter_query.where(Tripulante.oper.in_(oper_list))

    # Subconsulta com os IDs filtrados
    filtered_ids = filter_query.subquery()

    # Contagem total
    count_query = select(sql_func.count()).select_from(filtered_ids)
    total = await session.scalar(count_query) or 0

    # Query principal para buscar tripulantes com ordenação e paginação
    main_query = (
        select(Tripulante)
        .join(User)
        .join(PostoGrad)
        .where(Tripulante.id.in_(select(filtered_ids.c.id)))
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    trips = await session.scalars(main_query)
    items = trips.all()

    return paginated_response(
        items=list(items),
        total=total,
        page=page,
        per_page=per_page,
    )


@router.put(
    '/{id}', status_code=HTTPStatus.OK, response_model=ApiResponse[TripSchema]
)
async def update_trip(
    id: int,
    trip: BaseTrip,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, Depends(permission_checker('trips', 'update'))],
):
    query = select(Tripulante).where(
        Tripulante.id == id, Tripulante.uae == active_org
    )

    trip_search = await session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado',
        )

    db_trig = await session.scalar(
        select(Tripulante).where(
            (Tripulante.trig == trip.trig)
            & (Tripulante.uae == trip_search.uae)
            & (Tripulante.id != id)
        )
    )

    if db_trig:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Trigrama já registrado',
        )

    func_autorizada = await session.scalar(
        select(FuncaoUae.id).where(
            FuncaoUae.uae == active_org,
            FuncaoUae.func_cod == trip.func,
            FuncaoUae.active.is_(True),
        )
    )
    if not func_autorizada:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Função não operada pela organização',
        )

    proj_autorizado = await session.scalar(
        select(ProjetoAnv.modelo)
        .join(TenantProjeto, TenantProjeto.projeto == ProjetoAnv.id_projeto)
        .where(
            TenantProjeto.uae == active_org,
            ProjetoAnv.modelo == trip.proj,
        )
    )
    if not proj_autorizado:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Projeto não disponível para a organização',
        )

    before_patch: dict = {}
    after_patch: dict = {}
    for field in ('trig', 'active', 'func', 'oper', 'proj', 'data_op'):
        old_value = getattr(trip_search, field)
        new_value = getattr(trip, field)
        if old_value == new_value:
            continue
        before_patch[field] = (
            old_value.isoformat() if isinstance(old_value, date) else old_value
        )
        after_patch[field] = (
            new_value.isoformat() if isinstance(new_value, date) else new_value
        )

    # PUT com payload identico ao persistido nao e alteracao: sem esta
    # guarda o historico ganharia uma entrada de diff vazio.
    if after_patch:
        await log_user_action(
            session=session,
            user_id=user.id,
            action='patch',
            resource='trips',
            resource_id=trip_search.id,
            before=before_patch,
            after=after_patch,
        )

    trip_search.active = trip.active
    trip_search.trig = trip.trig
    trip_search.func = trip.func
    trip_search.oper = trip.oper
    trip_search.proj = trip.proj
    trip_search.data_op = trip.data_op

    await session.commit()
    await session.refresh(trip_search)

    return success_response(
        data=TripSchema.model_validate(trip_search),
        message='Tripulante atualizado com sucesso',
    )


@router.patch(
    '/{id}', status_code=HTTPStatus.OK, response_model=ApiResponse[TripSchema]
)
async def patch_trip(
    id: int,
    trip: TripUpdate,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, Depends(permission_checker('trips', 'update'))],
):
    query = select(Tripulante).where(
        Tripulante.id == id, Tripulante.uae == active_org
    )

    trip_search = await session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado',
        )

    patch = trip.model_dump(exclude_unset=True)

    # "data_op obrigatório quando oper != 'al'" precisa do valor
    # efetivo pós-merge (body ∪ persistido): alterar só `oper` para
    # 'op' sem `data_op` no body é inválido mesmo que `data_op` já
    # esteja preenchido no registro, e vice-versa.
    effective_oper = patch.get('oper', trip_search.oper)
    effective_data_op = patch.get('data_op', trip_search.data_op)
    if effective_oper != 'al' and effective_data_op is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data operacional é obrigatória para não-alunos',
        )

    if 'trig' in patch:
        db_trig = await session.scalar(
            select(Tripulante).where(
                (Tripulante.trig == patch['trig'])
                & (Tripulante.uae == trip_search.uae)
                & (Tripulante.id != id)
            )
        )

        if db_trig:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Trigrama já registrado',
            )

    if 'func' in patch:
        func_autorizada = await session.scalar(
            select(FuncaoUae.id).where(
                FuncaoUae.uae == active_org,
                FuncaoUae.func_cod == patch['func'],
                FuncaoUae.active.is_(True),
            )
        )
        if not func_autorizada:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Função não operada pela organização',
            )

    if 'proj' in patch:
        proj_autorizado = await session.scalar(
            select(ProjetoAnv.modelo)
            .join(
                TenantProjeto,
                TenantProjeto.projeto == ProjetoAnv.id_projeto,
            )
            .where(
                TenantProjeto.uae == active_org,
                ProjetoAnv.modelo == patch['proj'],
            )
        )
        if not proj_autorizado:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Projeto não disponível para a organização',
            )

    before_patch: dict = {}
    after_patch: dict = {}
    for field, new_value in patch.items():
        old_value = getattr(trip_search, field)
        if old_value == new_value:
            continue
        before_patch[field] = (
            old_value.isoformat() if isinstance(old_value, date) else old_value
        )
        after_patch[field] = (
            new_value.isoformat() if isinstance(new_value, date) else new_value
        )

    # Campo reenviado com o mesmo valor nao e alteracao: sem esta
    # guarda o historico ganharia uma entrada de diff vazio.
    if after_patch:
        await log_user_action(
            session=session,
            user_id=user.id,
            action='patch',
            resource='trips',
            resource_id=trip_search.id,
            before=before_patch,
            after=after_patch,
        )

    for field, value in patch.items():
        setattr(trip_search, field, value)

    await session.commit()
    await session.refresh(trip_search)

    return success_response(
        data=TripSchema.model_validate(trip_search),
        message='Tripulante atualizado com sucesso',
    )
