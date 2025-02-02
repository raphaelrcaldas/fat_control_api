from collections import defaultdict
from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Quad, QuadsGroup, Tripulante
from fcontrol_api.schemas.funcoes import BaseFunc, funcs, proj
from fcontrol_api.schemas.quads import (
    QuadPublic,
    QuadSchema,
    QuadsGroupSchema,
    QuadUpdate,
)
from fcontrol_api.schemas.tripulantes import uaes
from fcontrol_api.schemas.users import UserTrip

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_quad(quads: list[QuadSchema], session: Session):
    insert_quads = []
    for quad in quads:
        # VALUE 0 PARA LASTRO
        if quad.value is not None:
            db_quad = await session.scalar(
                select(Quad).where(
                    (Quad.value == quad.value)
                    & (Quad.type_id == quad.type_id)
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
            type_id=quad.type_id,
            trip_id=quad.trip_id,
        )  # type: ignore

        insert_quads.append(quad_db)

    session.add_all(insert_quads)
    await session.commit()

    return {'detail': 'Inserido com sucesso'}


@router.get(
    '/trip/{trip_id}',
    status_code=HTTPStatus.OK,
    response_model=list[QuadPublic],
)
async def quads_by_trip(trip_id: int, type_id: int, session: Session):
    query = select(Quad).where(
        (Quad.trip_id == trip_id) & (Quad.type_id == type_id)
    )

    result = await session.scalars(query)
    quads = result.all()

    # ORDENAR QUADRINHOS
    def order_quads(quad: Quad):
        if not quad.value:
            return date.fromtimestamp(0)

        return quad.value

    quads = sorted(quads, key=order_quads, reverse=True)

    return quads


@router.get('/', status_code=HTTPStatus.OK)
async def list_quads(
    session: Session,
    tipo_quad: int = 1,  # sobr preto
    funcao: funcs = 'mc',
    uae: uaes = '11gt',
    proj: proj = 'kc-390',
):
    query_quads = (
        select(Quad, Tripulante, Funcao)
        .select_from(Tripulante)
        .where((Tripulante.uae == uae) & (Tripulante.active == True))  # noqa: E712
        .join(
            Quad,
            ((Quad.trip_id == Tripulante.id) & (Quad.type_id == tipo_quad)),
            isouter=True,
        )
        .join(
            Funcao,
            (
                (Funcao.trip_id == Tripulante.id)
                & (Funcao.func == funcao)
                & (Funcao.oper != 'al')
                & (Funcao.proj == proj)
                & (Funcao.data_op != None)  # noqa: E711
            ),
        )
        .order_by(Funcao.data_op)
    )

    result = await session.execute(query_quads)

    group_quads = defaultdict(list)
    grou_info = {}
    for quad, trip, func in result.all():
        trip_schema = {'trig': trip.trig, 'id': trip.id}
        func_schema = BaseFunc.model_validate(func).model_dump()
        trip_schema['func'] = func_schema
        trip_schema['func'] = func_schema

        trip_schema['user'] = UserTrip.model_validate(trip.user).model_dump()
        grou_info[trip.trig] = trip_schema

        if quad:
            group_quads[trip.trig].append(
                QuadPublic.model_validate(quad).model_dump()
            )
        else:
            group_quads[trip.trig] = []

    response = []
    for trig, info in grou_info.items():
        response.append({
            'trip': info,
            'quads': group_quads[trig],
            'quads_len': len(group_quads[trig]),
        })

    # ORDENAR QUADRINHOS
    def order_quads(quad):
        if not quad['value']:
            return date.fromtimestamp(0)

        return quad['value']

    # FILTRAR ULTIMOS QUAD A PARTIR DO TRIP COM MENOR NUMERO DE QUAD
    min_length = min([len(crew['quads']) for crew in response])  # type: ignore
    n_slice = 0 if min_length == 0 else min_length - 1
    for crew in response:
        crew['quads'] = sorted(crew['quads'], key=order_quads)  # type: ignore
        crew['quads'] = crew['quads'][n_slice:]  # type: ignore

    return response


@router.delete('/{id}')
async def delete_quad(id: int, session: Session):
    quad = await session.scalar(select(Quad).where(Quad.id == id))

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    await session.delete(quad)
    await session.commit()

    return {'detail': 'Quadrinho deletado'}


@router.put('/{id}')
async def update_quad(id: int, quad: QuadUpdate, session: Session):
    db_quad = await session.scalar(select(Quad).where(Quad.id == id))

    if not db_quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    ss_quad = await session.scalar(
        select(Quad).where(
            (Quad.value == quad.value)
            & (Quad.type_id == db_quad.type_id)
            & (Quad.trip_id == quad.trip_id)
            & (Quad.id != id)
        )
    )

    if ss_quad:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Quadrinho já registrado',
        )

    for key, value in quad.model_dump(exclude_unset=True).items():
        if getattr(db_quad, key) != value:
            setattr(db_quad, key, value)

    await session.commit()

    return {'detail': 'Quadrinho atualizado'}


@router.get('/types', response_model=list[QuadsGroupSchema])
async def get_quads_type(uae: str, session: Session):
    quads = await session.scalars(
        select(QuadsGroup).where(QuadsGroup.uae == uae)
    )
    quads = quads.all()  # type: ignore

    for group in quads:
        group.types = sorted(group.types, key=lambda x: x.id)

    return quads
