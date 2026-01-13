from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.message import TripMessage
from fcontrol_api.schemas.pagination import PaginatedResponse
from fcontrol_api.schemas.tripulantes import (
    BaseTrip,
    TripSchema,
    TripWithFuncs,
)
from fcontrol_api.security import get_current_user

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=TripMessage)
async def create_trip(trip: TripSchema, session: Session):
    db_trig = await session.scalar(
        select(Tripulante).where(
            (Tripulante.trig == trip.trig) & (Tripulante.uae == trip.uae)
        )
    )

    if db_trig:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Trigrama já registrado',
        )

    db_trip = await session.scalar(
        select(Tripulante).where(
            (Tripulante.user_id == trip.user_id) & (Tripulante.uae == trip.uae)
        )
    )

    if db_trip:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Tripulante já registrado',
        )

    tripulante = Tripulante(
        user_id=trip.user_id,
        trig=trip.trig,
        active=trip.active,
        uae=trip.uae,
    )

    session.add(tripulante)
    await session.commit()
    await session.refresh(tripulante)

    return {'detail': 'Tripulante adicionado com sucesso', 'data': tripulante}


@router.get('/me', status_code=HTTPStatus.OK, response_model=TripWithFuncs)
async def get_my_trip(
    session: Session,
    current_user: User = Depends(get_current_user),
    uae: str = '11gt',
):
    """
    Retorna o tripulante do usuário autenticado.
    """
    trip = await session.scalar(
        select(Tripulante).where(
            Tripulante.user_id == current_user.id,
            Tripulante.uae == uae,
        )
    )

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado para este usuário',
        )

    return trip


@router.get('/{id}', status_code=HTTPStatus.OK, response_model=TripWithFuncs)
async def get_trip(id: int, session: Session):
    trip = await session.scalar(select(Tripulante).where(Tripulante.id == id))

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    return trip


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=PaginatedResponse[TripWithFuncs],
)
async def list_trips(
    session: Session,
    uae: str = '11gt',
    active: bool = True,
    page: int = 1,
    per_page: int = 10,
    search: str | None = None,
    p_g: str | None = None,
    func: str | None = None,
    oper: str | None = None,
):
    # Flag para saber se precisa fazer join com Funcao
    needs_func_join = bool(func or oper)

    # Query base para filtrar IDs
    filter_query = (
        select(Tripulante.id)
        .join(User)
        .join(PostoGrad)
        .where(
            User.active,
            Tripulante.active == active,
            Tripulante.uae == uae,
        )
    )

    # Filtro de busca por nome/trigrama
    if search:
        search_term = search.lower()
        filter_query = filter_query.where(
            (Tripulante.trig.ilike(f'%{search_term}%'))
            | (User.nome_guerra.ilike(f'%{search_term}%'))
        )

    # Filtro por posto/graduação
    if p_g:
        p_g_list = [pg.strip() for pg in p_g.split(',') if pg.strip()]
        if p_g_list:
            filter_query = filter_query.where(User.p_g.in_(p_g_list))

    # Filtro por função - requer join com Funcao
    if func:
        func_list = [f.strip() for f in func.split(',') if f.strip()]
        if func_list:
            filter_query = filter_query.join(
                Funcao, Tripulante.id == Funcao.trip_id
            ).where(Funcao.func.in_(func_list))

    # Filtro por operacionalidade - requer join com Funcao (se não fez ainda)
    if oper:
        oper_list = [o.strip() for o in oper.split(',') if o.strip()]
        if oper_list:
            if not func:  # Se não fez join com Funcao ainda
                filter_query = filter_query.join(
                    Funcao, Tripulante.id == Funcao.trip_id
                )
            filter_query = filter_query.where(Funcao.oper.in_(oper_list))

    # Distinct para evitar duplicatas quando há joins com Funcao
    if needs_func_join:
        filter_query = filter_query.distinct()

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

    # Cálculo de páginas
    pages = (total + per_page - 1) // per_page if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.put('/{id}', status_code=HTTPStatus.OK, response_model=TripMessage)
async def update_trip(id: int, trip: BaseTrip, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip_search = await session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
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

    trip_search.active = trip.active
    trip_search.trig = trip.trig

    await session.commit()
    await session.refresh(trip_search)

    return {'detail': 'Tripulante atualizado com sucesso', 'data': trip_search}


# @router.delete('/{id}')
# def delete_trip(id: int, session: Session):
#     query = select(Tripulante).where(Tripulante.id == id)

#     trip: Tripulante = session.scalar(query)

#     if not trip:
#         raise HTTPException(
#             status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
#         )

#     session.delete(trip)
#     session.commit()

#     return {'detail': 'Crew member deleted'}
