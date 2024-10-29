from functools import reduce
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Quad, Tripulante
from fcontrol_api.schemas.funcs import funcs, proj, uae
from fcontrol_api.schemas.quads import (
    QuadList,
    QuadPublic,
    QuadSchema,
    QuadType,
    QuadUpdate,
)

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=QuadPublic)
def create_quad(quad: QuadSchema, session: Session):
    db_trip = session.scalar(
        select(Tripulante).where((Tripulante.id == quad.trip_id))
    )

    if not db_trip:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Crew Member doesnt exists',
        )

    # VALUE 0 PARA LASTRO
    if quad.value != 0:
        db_quad = session.scalar(
            select(Quad).where(
                (Quad.value == quad.value)
                & (Quad.type == quad.type)
                & (Quad.trip_id == quad.trip_id)
            )
        )

        if db_quad:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Quadrinho já registrado',
            )

    db_quad = Quad(
        value=quad.value,
        description=quad.description,
        type=quad.type,
        trip_id=quad.trip_id,
    )

    session.add(db_quad)
    session.commit()
    session.refresh(db_quad)

    return db_quad


@router.get('/{quad_id}', status_code=HTTPStatus.OK, response_model=QuadPublic)
def get_quad(session: Session, id):
    quad = session.scalar(select(Quad).where(Quad.id == id))

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found.'
        )

    return quad


@router.get('/', status_code=HTTPStatus.OK)  # , response_model=QuadList)
def list_quads(
    session: Session, funcao: funcs, uae: uae, proj: proj, tipo_quad: QuadType
):
    query_funcs = select(Funcao).where(
        (Funcao.func == funcao) & (Funcao.oper != 'al') & (Funcao.proj == proj)
    )
    funcs = session.scalars(query_funcs).all()

    # ADICIONANDO INFORMAÇÕES DO TRIPULANTE
    for func in funcs:
        query_trip = select(Tripulante).where(Tripulante.id == func.trip_id)
        trip = session.scalar(query_trip)
        setattr(func, 'trip', trip)

    # FILTRAR TRIPULANTES ATIVOS E DA UAE
    trips = list(
        filter(lambda x: (x.trip.active) and (x.trip.uae == uae), funcs)
    )

    # OBTENDO QUADRINHOS DE CADA TRIP
    def create_quads(initial: dict, func: Funcao):
        query_quads = select(Quad).where(
            (Quad.trip_id == func.trip_id) & (Quad.type == tipo_quad)
        )

        quads = session.scalars(query_quads).all()

        initial[func.trip.trig] = quads

        return initial

    return reduce(create_quads, trips, {})


@router.delete('/{id}')
def delete_quad(id: int, session: Session):
    quad = session.scalar(select(Quad).where(Quad.id == id))

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    session.delete(quad)
    session.commit()

    return {'detail': 'Quad deleted'}


@router.patch('/{id}', response_model=QuadPublic)
def patch_quad(id: int, session: Session, quad: QuadUpdate):
    db_quad = session.scalar(select(Quad).where(Quad.id == id))

    if not db_quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found.'
        )

    for key, value in quad.model_dump(exclude_unset=True).items():
        setattr(db_quad, key, value)

    session.add(db_quad)
    session.commit()
    session.refresh(db_quad)

    return db_quad
