from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.schemas.message import TripMessage
from fcontrol_api.schemas.tripulantes import (
    BaseTrip,
    TripSchema,
    TripWithFuncs,
)

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
    query = select(Tripulante).where(
        (Tripulante.active == active) & (Tripulante.uae == uae)
    )

    trips = await session.scalars(query)

    return trips.all()


@router.put('/{id}', status_code=HTTPStatus.OK, response_model=TripMessage)
async def update_trip(id, trip: BaseTrip, session: Session):
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
