from http import HTTPStatus
from typing import Annotated, Sequence

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Tripulante
from fcontrol_api.schemas.message import TripMessage
from fcontrol_api.schemas.tripulantes import (
    BaseTrip,
    TripSchema,
    TripWithFuncs,
)

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=TripMessage)
def create_trip(trip: TripSchema, session: Session):
    db_trig = session.scalar(
        select(Tripulante).where(
            (Tripulante.trig == trip.trig) & (Tripulante.uae == trip.uae)
        )
    )

    if db_trig:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Trigrama já registrado',
        )

    db_trip = session.scalar(
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
        user_id=trip.user_id, trig=trip.trig, active=trip.active, uae=trip.uae
    )

    session.add(tripulante)
    session.commit()

    return {'detail': 'Tripulante adicionado com sucesso', 'data': tripulante}


@router.get('/{id}', response_model=TripWithFuncs)
def get_trip(id, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip: Tripulante | None = session.scalar(query)

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    return trip


@router.get('/', status_code=HTTPStatus.OK, response_model=list[TripWithFuncs])
def list_trips(session: Session, uae='11gt', active=True):
    query = select(Tripulante).where(
        (Tripulante.active == active) & (Tripulante.uae == uae)
    )

    trips: Sequence[Tripulante] | None = session.scalars(query).all()

    return trips


@router.put('/{id}', status_code=HTTPStatus.OK, response_model=TripMessage)
def update_trip(id, trip: BaseTrip, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip_search: Tripulante | None = session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    db_trig: Tripulante | None = session.scalar(
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

    session.commit()
    session.refresh(trip_search)

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
