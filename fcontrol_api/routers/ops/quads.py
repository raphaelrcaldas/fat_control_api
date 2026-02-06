from collections import defaultdict
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import contains_eager, selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.quads import Quad, QuadsGroup, QuadsType
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.funcoes import BaseFunc, funcs, proj
from fcontrol_api.schemas.quads import (
    QuadPublic,
    QuadSchema,
    QuadsGroupSchema,
    QuadUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.tripulantes import uaes
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.utils.responses import success_response

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=ApiResponse[None]
)
async def create_quad(quads: list[QuadSchema], session: Session):
    insert_quads = []
    for quad in quads:
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
        )

        insert_quads.append(quad_db)

    session.add_all(insert_quads)
    await session.commit()

    return success_response(message='Quadrinho inserido com sucesso')


@router.get(
    '/trip/{trip_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[QuadPublic]],
)
async def quads_by_trip(trip_id: int, type_id: int, session: Session):
    query = (
        select(Quad)
        .where((Quad.trip_id == trip_id) & (Quad.type_id == type_id))
        .order_by(
            Quad.value.desc().nulls_last()
        )  # ordena NULLs primeiro, depois valores em DESC
    )

    result = await session.scalars(query)
    quads = result.all()

    return success_response(data=[QuadPublic.model_validate(q) for q in quads])


@router.get('/', status_code=HTTPStatus.OK, response_model=ApiResponse[list])
async def list_quads(
    session: Session,
    tipo_quad: int = 1,  # sobr preto
    funcao: funcs = 'mc',
    uae: uaes = '11gt',
    proj: proj = 'kc-390',
):
    # 1. CTE para obter os IDs dos tripulantes que correspondem aos filtros
    trip_ids_cte = (
        select(Tripulante.id)
        .join(Funcao)
        .where(
            Tripulante.uae == uae,
            Tripulante.active,
            Funcao.func == funcao,
            Funcao.oper != 'al',
            Funcao.proj == proj,
            Funcao.data_op.is_not(None),
        )
        .cte('trip_ids_cte')
    )

    # 2. CTE para contar o total de quadrinhos de cada tripulante
    quad_counts_cte = (
        select(Quad.trip_id, func.count(Quad.id).label('total_quads'))
        .where(
            Quad.trip_id.in_(select(trip_ids_cte.c.id)),
            Quad.type_id == tipo_quad,
        )
        .group_by(Quad.trip_id)
        .cte('quad_counts_cte')
    )

    # 3. Query principal para buscar os tripulantes e a contagem total
    # Faz um LEFT JOIN com a contagem, para incluir tripulantes sem quadrinhos
    trip_query = (
        select(Tripulante, quad_counts_cte.c.total_quads)
        .join(Tripulante.funcs)
        .outerjoin(quad_counts_cte, Tripulante.id == quad_counts_cte.c.trip_id)
        .options(
            selectinload(Tripulante.user).selectinload(User.posto),
            contains_eager(Tripulante.funcs),
        )
        .where(Tripulante.id.in_(select(trip_ids_cte.c.id)))
        .order_by(Funcao.data_op)
    )

    trips_result = await session.execute(trip_query)
    trip_data = (
        trips_result.unique().all()
    )  # Retorna tuplas (Tripulante, total_quads)

    if not trip_data:
        return success_response(data=[])

    # Extrai os IDs e o min_length dos resultados
    trip_ids = [trip.id for trip, _ in trip_data]
    min_length = min(
        (total_quads if total_quads is not None else 0)
        for _, total_quads in trip_data
    )

    # 4. Query avançada para buscar APENAS os quadrinhos já fatiados
    n_slice = 0 if min_length == 0 else min_length - 1

    # CTE para rankear os quadrinhos
    ranked_quads_cte = (
        select(
            Quad,
            func
            .row_number()
            .over(
                partition_by=Quad.trip_id,
                order_by=Quad.value.asc().nullsfirst(),
            )
            .label('rn'),
        )
        .where(Quad.trip_id.in_(trip_ids), Quad.type_id == tipo_quad)
        .cte('ranked_quads')
    )

    # Query final para buscar os quadrinhos já fatiados
    final_quads_query = select(ranked_quads_cte).where(
        ranked_quads_cte.c.rn > n_slice
    )

    quads_result = await session.execute(final_quads_query)
    all_quads_data = quads_result.mappings()

    # 5. Agrupa os dicionários de dados por trip_id
    quads_by_trip_id = defaultdict(list)
    for q_data in all_quads_data:
        quads_by_trip_id[q_data['trip_id']].append(q_data)

    # 6. Monta a resposta final
    response = []
    for trip, total_quads in trip_data:
        relevant_func = trip.funcs[0] if trip.funcs else None
        trip_info = {
            'trig': trip.trig,
            'id': trip.id,
            'user': UserPublic.model_validate(trip.user).model_dump(),
            'func': (
                BaseFunc.model_validate(relevant_func).model_dump()
                if relevant_func
                else None
            ),
        }

        crew_quads_data = quads_by_trip_id[trip.id]
        response.append({
            'trip': trip_info,
            'quads': [
                QuadPublic.model_validate(q).model_dump()
                for q in crew_quads_data
            ],
            'quads_len': total_quads if total_quads is not None else 0,
        })

    return success_response(data=response)


@router.delete('/{id}', response_model=ApiResponse[None])
async def delete_quad(id: int, session: Session):
    quad = await session.scalar(select(Quad).where(Quad.id == id))

    if not quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Quad not found'
        )

    await session.delete(quad)
    await session.commit()

    return success_response(message='Quadrinho deletado')


@router.put('/{id}', response_model=ApiResponse[None])
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

    return success_response(message='Quadrinho atualizado')


@router.get('/types', response_model=ApiResponse[list[QuadsGroupSchema]])
async def get_quads_type(uae: str, session: Session):
    quads = await session.scalars(
        select(QuadsGroup)
        .where(QuadsGroup.uae == uae)
        .options(selectinload(QuadsGroup.types).selectinload(QuadsType.funcs))
    )
    quads = quads.all()  # type: ignore

    for group in quads:
        group.types = sorted(group.types, key=lambda x: x.id)

        for type_quad in group.types:
            funcs = [e.func for e in type_quad.funcs]
            setattr(type_quad, 'funcs_list', funcs)

    return success_response(data=list(quads))
