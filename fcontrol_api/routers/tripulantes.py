from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Tripulante, User
from fcontrol_api.schemas.tripulantes import (
    TripSchema,
    TripsListWithFuncs,
    TripUpdate,
    TripWithFuncs,
)

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.post('/', response_model=TripSchema, status_code=HTTPStatus.CREATED)
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
    session.refresh(tripulante)

    return tripulante


@router.get('/{id}', response_model=TripWithFuncs)
def get_trip(id, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip: Tripulante = session.scalar(query)

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew not found'
        )

    query_user = select(User).where(trip.user_id == User.id)
    user = session.scalar(query_user)
    setattr(trip, 'user', user)

    query_funcao = select(Funcao).where(id == Funcao.trip_id)
    funcs = session.scalars(query_funcao).all()
    setattr(trip, 'funcs', funcs)

    return trip


@router.get('/', response_model=TripsListWithFuncs)
def list_trips(uae: str, active: bool, session: Session):
    query = select(Tripulante).where(
        (Tripulante.active == active) & (Tripulante.uae == uae)
    )

    trips: list[Tripulante] = session.scalars(query).all()

    for trip in trips:
        query_user = select(User).where(trip.user_id == User.id)
        user = session.scalar(query_user)
        setattr(trip, 'user', user)

        query_funcao = select(Funcao).where(trip.id == Funcao.trip_id)
        funcs = session.scalars(query_funcao).all()
        setattr(trip, 'funcs', funcs)

    return {'data': trips}


@router.put('/{id}')
def update_trip(id, trip: TripUpdate, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip_search: Tripulante = session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    for key, value in trip.model_dump(exclude_unset=True).items():
        setattr(trip_search, key, value)

    session.commit()
    session.refresh(trip_search)

    return trip_search


@router.delete('/{id}')
def delete_trip(id: int, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip: Tripulante = session.scalar(query)

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    session.delete(trip)
    session.commit()

    return {'detail': 'Crew member deleted'}
