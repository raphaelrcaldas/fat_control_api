from collections import defaultdict
from datetime import date, timedelta
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.funcoes import BaseFunc
from fcontrol_api.schemas.indisp import BaseIndisp, IndispOut, IndispSchema
from fcontrol_api.schemas.users import UserTrip
from fcontrol_api.security import get_current_user

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/indisp', tags=['indisp'])


@router.get('/')
async def get_crew_indisp(session: Session, funcao: str, uae: str):
    date_ini = date.today() - timedelta(days=30)

    query = (
        select(Indisp, Tripulante, Funcao)
        .select_from(Funcao)
        .where((Funcao.func == funcao))
        .join(
            Tripulante,
            (Tripulante.id == Funcao.trip_id)
            & (Tripulante.uae == uae)
            & (Tripulante.active),
        )
        .join(
            Indisp,
            (
                (Indisp.user_id == Tripulante.user_id)
                & (Indisp.date_end >= date_ini)
            ),
            isouter=True,
        )
        .order_by(Indisp.date_end.desc())
    )

    db_indisp = await session.execute(query)

    group_indisp = defaultdict(list)
    grou_info = {}
    for indisp, trip, inner_funcao in db_indisp.all():
        trip_schema = {'trig': trip.trig, 'id': trip.id}
        func_schema = BaseFunc.model_validate(inner_funcao).model_dump()

        trip_schema['func'] = func_schema
        trip_schema['user'] = UserTrip.model_validate(trip.user).model_dump()
        grou_info[trip.trig] = trip_schema

        if indisp:
            group_indisp[trip.trig].append(
                IndispOut.model_validate(indisp).model_dump()
            )
        else:
            group_indisp[trip.trig] = []

    response = [
        {'trip': info, 'indisps': group_indisp[trig]}
        for trig, info in grou_info.items()
    ]

    def order(trip):
        user = trip['trip']['user']
        pg_index = user['posto']['ant']
        ult_promo = user['ult_promo']
        ant = user['ant_rel']

        return (pg_index, ult_promo, ant)

    response = sorted(response, key=order)

    return response


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_indisp(
    indisp: IndispSchema,
    session: Session,
    user: User = Depends(get_current_user),
):
    if indisp.date_end < indisp.date_start:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data Fim deve ser maior ou igual a data início',
        )

    db_indisp = await session.scalar(
        select(Indisp).where(
            (Indisp.user_id == indisp.user_id)
            & (Indisp.date_start == indisp.date_start)
            & (Indisp.date_end == indisp.date_end)
            & (Indisp.mtv == indisp.mtv)
        )
    )

    if db_indisp:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Indisponibilidade já registrada',
        )

    new_indisp = Indisp(
        user_id=indisp.user_id,
        date_start=indisp.date_start,
        date_end=indisp.date_end,
        mtv=indisp.mtv,
        obs=indisp.obs,
        created_by=user.id,
    )  # type: ignore

    session.add(new_indisp)
    await session.commit()

    return {'detail': 'Indisponibilidade adicionada com sucesso'}


@router.get('/user/{id}', response_model=list[IndispOut])
async def get_indisp_user(id: int, session: Session):
    date_ini = date.today() - timedelta(days=15)

    db_indisps = await session.scalars(
        select(Indisp)
        .where((Indisp.user_id == id) & (Indisp.date_end >= date_ini))
        .order_by(Indisp.date_end.desc())
    )

    indisps = db_indisps.all()

    return indisps


@router.delete('/{id}')
async def delete_indisp(id: int, session: Session):
    indisp = await session.scalar(select(Indisp).where(Indisp.id == id))

    if not indisp:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Indisponibilidade not found',
        )

    await session.delete(indisp)
    await session.commit()

    return {'detail': 'Indisponibilidade deletada'}


@router.put('/{id}')
async def update_indisp(id: int, indisp: BaseIndisp, session: Session):
    db_indisp = await session.scalar(select(Indisp).where(Indisp.id == id))

    if not db_indisp:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Indisp not found'
        )

    ss_indisp = await session.scalar(
        select(Indisp).where(
            (Indisp.user_id == db_indisp.user_id)
            & (Indisp.date_start == indisp.date_start)
            & (Indisp.date_end == indisp.date_end)
            & (Indisp.mtv == indisp.mtv)
            & (Indisp.obs == indisp.obs)
        )
    )

    if ss_indisp:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Indisponibilidade já registrada',
        )

    for key, value in indisp.model_dump(exclude_unset=True).items():
        if getattr(db_indisp, key) != value:
            setattr(db_indisp, key, value)

    await session.commit()

    return {'detail': 'Indisponibilidade atualizada'}
