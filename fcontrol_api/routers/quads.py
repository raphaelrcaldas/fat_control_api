from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import FuncList, Quad, QuadType, Tripulante
from fcontrol_api.schemas import (
    Message,
    QuadList,
    QuadPublic,
    QuadSchema,
    QuadUpdate,
)

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=QuadPublic)
def create_quad(quad: QuadSchema, session: Session):
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
            detail='quad already registered',
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
    query = (
        select(Quad, Tripulante)
        .join(Tripulante, Quad.trip_id == Tripulante.id)
        .where(Quad.id == id)
    )

    quad = session.scalar(query)

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found.'
        )

    return quad


@router.get('/', status_code=HTTPStatus.OK, response_model=QuadList)
def list_quads(session: Session, type: QuadType, funcao: FuncList):
    query = (
        select(Quad, Tripulante)
        .join(Tripulante, Quad.trip_id == Tripulante.id)
        .where(Quad.type == type)
    )

    quads = session.execute(query.filter(Tripulante.func == funcao)).all()
    quads = [q[0] for q in quads]

    return {'quads': quads}


@router.delete('/{id}', response_model=Message)
def delete_quad(quad_id: int, session: Session):
    query = select(Quad).where(Quad.id == quad_id)

    quad = session.scalar(query)

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    session.delete(quad)
    session.commit()

    return {'message': 'Quad deleted'}


@router.patch('/{quad_id}', response_model=QuadPublic)
def patch_quad(quad_id: int, session: Session, quad: QuadUpdate):
    db_quad = session.scalar(select(Quad).where(Quad.id == quad_id))

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
