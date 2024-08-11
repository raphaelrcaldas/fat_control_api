from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Tripulante
from fcontrol_api.schemas.message import Message
from fcontrol_api.schemas.tripulantes import (
    TripList,
    TripPublic,
    TripSchema,
    TripSchemaUpdate,
)

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.post('/', response_model=TripPublic, status_code=HTTPStatus.CREATED)
def create_trip(trip: TripSchema, session: Session):
    db_trig = session.scalar(
        select(Tripulante).where(Tripulante.trig == trip.trig)
    )

    if db_trig:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='trigram already registered',
        )

    db_trip = Tripulante(
        id=trip.id,
        trig=trip.trig,
        func=trip.func,
        oper=trip.oper,
        active=True,
    )

    session.add(db_trip)
    session.commit()
    session.refresh(db_trip)

    return db_trip


@router.get('/{user_id}', response_model=TripPublic)
def get_trip(user_id, session: Session):
    query = select(Tripulante).where(Tripulante.id == user_id)

    trip_search = session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew not found'
        )

    return trip_search


@router.get('/', response_model=TripList)
def list_trips(
    session: Session,
    oper: str = Query(None),
    funcao: str = Query(None),
    id: str = Query(None),
    active: bool = True,
):
    query = select(Tripulante).where(Tripulante.active == active)

    if oper:
        query = query.filter(Tripulante.oper == oper)

    if funcao:
        query = query.filter(Tripulante.oper == funcao)

    if id:
        query = query.filter(Tripulante.id == id)

    trips = session.scalars(query).all()

    return {'trips': trips}


@router.put('/{user_id}', response_model=TripPublic)
def update_trip(user_id, trip: TripSchemaUpdate, session: Session):
    query = select(Tripulante).where(Tripulante.id == user_id)

    trip_search: Tripulante = session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew not found'
        )

    for key, value in trip.model_dump(exclude_unset=True).items():
        setattr(trip_search, key, value)

    session.commit()
    session.refresh(trip_search)

    return trip_search


@router.delete('/{user_id}', response_model=Message)
def delete_trip(user_id: int, session: Session):
    query = select(Tripulante).where(Tripulante.id == user_id)

    user_search: Tripulante = session.scalar(query)

    if not user_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='crew not found'
        )

    session.delete(user_search)
    session.commit()

    return {'message': 'Crew deleted'}
