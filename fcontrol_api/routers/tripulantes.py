from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Tripulante
from fcontrol_api.schemas.tripulantes import (
    TripSchema,
    TripsListWithFuncs,
    TripUpdate,
    TripWithFuncs,
)

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/trips', tags=['trips'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=TripSchema)
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
        user_id=trip.user_id, trig=trip.trig, active=True, uae=trip.uae
    )

    session.add(tripulante)
    session.commit()

    funcoes = [
        Funcao(trip_id=tripulante.id, func=f.func, oper=f.oper, proj=f.proj)
        for f in trip.funcs
    ]

    session.add_all(funcoes)
    session.commit()

    session.refresh(tripulante)

    return tripulante


@router.get('/{id}', response_model=TripWithFuncs)
def get_trip(id, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip: Tripulante = session.scalar(query)

    if not trip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    return trip


@router.get('/', response_model=TripsListWithFuncs)
def list_trips(uae: str, active: bool, session: Session):
    query = select(Tripulante).where(
        (Tripulante.active == active) & (Tripulante.uae == uae)
    )

    trips: list[Tripulante] = session.scalars(query).all()

    return {'data': trips}


@router.put('/{id}', response_model=TripWithFuncs)
def update_trip(id, trip: TripUpdate, session: Session):
    query = select(Tripulante).where(Tripulante.id == id)

    trip_search: Tripulante = session.scalar(query)

    if not trip_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew member not found'
        )

    trip_search.active = trip.active
    trip_search.trig = trip.trig

    for funcao in trip.funcs:
        query_func = select(Funcao).where(
            (Funcao.func == funcao.func)
            & (Funcao.proj == funcao.proj)
            & (Funcao.trip_id == trip_search.id)
        )
        func_search = session.scalar(query_func)

        if func_search:
            for key, value in funcao.model_dump(exclude_unset=True).items():
                setattr(func_search, key, value)
        else:
            new_func = Funcao(
                trip_id=trip_search.id,
                func=funcao.func,
                oper=funcao.oper,
                proj=funcao.proj,
            )

            session.add(new_func)

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
