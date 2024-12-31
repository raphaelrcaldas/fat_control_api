from collections import defaultdict
from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Quad, Tripulante
from fcontrol_api.schemas.funcoes import BaseFunc, funcs, proj
from fcontrol_api.schemas.quads import (
    QuadPublic,
    QuadSchema,
    QuadUpdate,
)
from fcontrol_api.schemas.tripulantes import TripSchema, uaes

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
    '/trip/{trip_id}',
    status_code=HTTPStatus.OK,
    response_model=list[QuadPublic],
)
def quads_by_trip(trip_id: int, type: str, session: Session):
    query = (
        select(Quad)
        .where((Quad.trip_id == trip_id) & (Quad.type == type))
        .order_by(Quad.value)
    )

    quads = session.scalars(query)

    return quads


@router.get(
    '/',
    status_code=HTTPStatus.OK,
)
def list_quads(
    session: Session,
    tipo_quad: str = 'sobr-preto',
    funcao: funcs = 'mc',
    uae: uaes = '11gt',
    proj: proj = 'kc-390',
):
    query_quads = (
        select(Quad, Tripulante, Funcao)
        .select_from(Tripulante)
        .where((Tripulante.uae == uae) & (Tripulante.active == True))
        .join(
            Quad,
            ((Quad.trip_id == Tripulante.id) & (Quad.type == tipo_quad)),
            isouter=True,
        )
        .join(
            Funcao,
            (
                (Funcao.trip_id == Tripulante.id)
                & (Funcao.func == funcao)
                & (Funcao.oper != 'al')
                & (Funcao.proj == proj)
                & (Funcao.data_op != None)
            ),
        )
        .order_by(Quad.value)
    )

    quads = session.execute(query_quads).all()

    groupQuads = defaultdict(list)
    groupInfo = {}
    for quad, trip, func in quads:
        trip_schema = {'trig': trip.trig, 'id': trip.id}
        func_schema = BaseFunc.model_validate(func).model_dump(
            exclude={'proj'}
        )
        trip_schema['func'] = func_schema
        groupInfo[trip.trig] = trip_schema

        if quad:
            quad = QuadPublic.model_validate(quad).model_dump(exclude={'type'})
            groupQuads[trip.trig].append(quad)
        else:
            groupQuads[trip.trig] = []

    response = []
    for trig, info in groupInfo.items():
        response.append({'trip': info, 'quads': groupQuads[trig]})

    # ORDENAR QUADRINHOS
    def order_quads(quad):
        if not quad['value']:
            return date.fromtimestamp(0)

        return quad['value']

    # FILTRAR ULTIMOS QUAD A PARTIR DO TRIP COM MENOR NUMERO DE QUAD
    min_length = min([len(crew['quads']) for crew in response])
    n_slice = 0 if min_length == 0 else min_length - 1
    for crew in response:
        crew['quads'] = sorted(crew['quads'], key=order_quads)  # order
        crew['quads'] = crew['quads'][n_slice:]
        print(crew['trip']['trig'], len(crew['quads']))

    return response


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
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    for key, value in quad.model_dump(exclude_unset=True).items():
        setattr(db_quad, key, value)

    session.commit()
    session.refresh(db_quad)

    return db_quad
