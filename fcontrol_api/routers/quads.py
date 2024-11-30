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
    QuadPublic,
    QuadSchema,
    QuadUpdate,
    ResQuad,
)

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=list[QuadPublic]
)
def create_quad(quads: list[QuadSchema], session: Session):
    insert_quads = []
    for quad in quads:
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

        quad_db = Quad(
            value=quad.value,
            description=quad.description,
            type=quad.type,
            trip_id=quad.trip_id,
        )

        insert_quads.append(quad_db)

    session.add_all(insert_quads)
    session.commit()

    return insert_quads


@router.get(
    '/trip', status_code=HTTPStatus.OK, response_model=list[QuadPublic]
)
def quads_by_trip(session: Session, trip_id: int, type: str):
    query = select(Quad).where((Quad.trip_id == trip_id) & (Quad.type == type))

    quads = session.scalars(query)

    return quads


@router.get('/', status_code=HTTPStatus.OK, response_model=list[ResQuad])
def list_quads(
    session: Session, funcao: funcs, uae: uae, proj: proj, tipo_quad: str
):
    query_funcs = select(Funcao).where(
        (Funcao.func == funcao)
        & (Funcao.oper != 'al')
        & (Funcao.proj == proj)
        & (Funcao.data_op != None)  # noqa: E711
    )
    funcs = session.scalars(query_funcs).all()

    # ADICIONANDO INFORMAÇÕES DO TRIPULANTE
    for func in funcs:
        func: Funcao
        query_trip = select(Tripulante).where(Tripulante.id == func.trip_id)
        trip = session.scalar(query_trip)
        setattr(func, 'trip', trip)

    # FILTRAR TRIPULANTES ATIVOS E DA UAE
    trips = list(
        filter(lambda x: (x.trip.active) and (x.trip.uae == uae), funcs)
    )

    # OBTENDO QUADRINHOS DE CADA TRIP
    def create_quads(initial: list, func: Funcao):
        query_quads = select(Quad).where(
            (Quad.trip_id == func.trip_id) & (Quad.type == tipo_quad)
        )

        quads = session.scalars(query_quads).all()

        setattr(func, 'quads', quads)

        return [*initial, func]

    trip_with_quads = reduce(create_quads, trips, [])

    # FILTRAR ULTIMOS QUAD A PARTIR DO TRIP COM MENOR NUMERO DE QUAD
    min_length = min([len(crew.quads) for crew in trip_with_quads])

    for crew in trip_with_quads:
        crew.quads = crew.quads[min_length - 1 :]

    return trip_with_quads


@router.delete('/{id}')
def delete_quad(id: int, session: Session):
    quad = session.scalar(select(Quad).where(Quad.id == id))

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    session.delete(quad)
    session.commit()

    return {'detail': 'Quadrinho deletado'}


@router.patch('/{id}', status_code=HTTPStatus.OK, response_model=QuadPublic)
def patch_quad(id: int, session: Session, quad: QuadUpdate):
    db_quad = session.scalar(select(Quad).where(Quad.id == id))

    if not db_quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found.'
        )

    for key, value in quad.model_dump(exclude_unset=True).items():
        setattr(db_quad, key, value)

    session.commit()
    session.refresh(db_quad)

    return db_quad
