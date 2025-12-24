from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.message import TripMessage
from fcontrol_api.schemas.tripulantes import (
    BaseTrip,
    TripSchema,
    TripSearchResult,
    TripWithFuncs,
)

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.get(
    '/search', status_code=HTTPStatus.OK, response_model=list[TripSearchResult]
)
async def search_trips(
    session: Session,
    func: str,
    q: str = '',
    proj: str = 'kc-390',
    uae: str = '11gt',
):
    """
    Busca tripulantes por função e projeto para seleção em ordens de missão.

    - **func**: Função requerida (pil, mc, lm, oe, os, tf)
    - **proj**: Projeto/aeronave (padrão: kc-390)
    - **q**: Termo de busca (trigrama ou nome)
    - **uae**: Unidade aérea (padrão: 11gt)
    """
    # Query base: tripulantes ativos com a função e projeto especificados
    # Fazemos import do PostoGrad aqui para evitar circular import
    from fcontrol_api.models.public.posto_grad import PostoGrad

    query = (
        select(
            Tripulante.id,
            Tripulante.trig,
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            User.id_fab,
            Funcao.oper,
            PostoGrad.ant.label('posto_ant'),
            User.ult_promo,
            User.ant_rel,
        )
        .join(User, Tripulante.user_id == User.id)
        .join(Funcao, Tripulante.id == Funcao.trip_id)
        .join(PostoGrad, User.p_g == PostoGrad.short)
        .where(
            User.active,
            Tripulante.active,
            Tripulante.uae == uae,
            Funcao.func == func,
            Funcao.proj == proj,
        ).order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
        )
    )

    # Filtro de busca (trigrama ou nome)
    if q:
        search_term = q.lower()
        query = query.where(
            (Tripulante.trig.ilike(f'{search_term}%'))
            | (User.nome_guerra.ilike(f'%{search_term}%'))
            | (User.nome_completo.ilike(f'%{search_term}%'))
        )

    # Limitar resultados e ordenar por trigrama
    query = query.order_by(Tripulante.trig).limit(10)

    result = await session.execute(query)
    rows = result.all()

    return [
        TripSearchResult(
            id=row.id,
            trig=row.trig,
            p_g=row.p_g,
            nome_guerra=row.nome_guerra,
            oper=row.oper,
            posto_ant=row.posto_ant,
            ult_promo=row.ult_promo,
            ant_rel=row.ant_rel,
            id_fab=row.id_fab,
        )
        for row in rows
    ]


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
    )  # type: ignore

    session.add(tripulante)
    await session.commit()
    await session.refresh(tripulante)

    return {'detail': 'Tripulante adicionado com sucesso', 'data': tripulante}


@router.get('/{id}', status_code=HTTPStatus.OK, response_model=TripWithFuncs)
async def get_trip(id: int, session: Session):
    trip = await session.scalar(select(Tripulante).where(Tripulante.id == id))

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    return trip


@router.get('/', status_code=HTTPStatus.OK, response_model=list[TripWithFuncs])
async def list_trips(session: Session, uae: str = '11gt', active: bool = True):
    query = (
        select(Tripulante)
        .join(User)
        .where(User.active, Tripulante.active == active, Tripulante.uae == uae)
    )

    trips = await session.scalars(query)

    return trips.all()


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
