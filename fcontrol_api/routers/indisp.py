from collections import defaultdict
from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Indisp, Tripulante
from fcontrol_api.schemas.indisp import BaseIndisp, IndispOut, IndispSchema

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/indisp', tags=['indisp'])


@router.get('/')
async def get_crew_indisp(session: Session, funcao: str):
    date_ini = datetime.now() - timedelta(days=15)

    query = (
        select(Indisp, Tripulante)
        .select_from(Funcao)
        .where(Funcao.func == funcao)
        .join(Tripulante, Tripulante.id == Funcao.trip_id)
        .join(
            Indisp,
            (
                (Indisp.user_id == Tripulante.user_id)
                & (Indisp.date_end >= date_ini)
            ),
            isouter=True,
        )
        .order_by(Indisp.date_end)
    )

    db_indisp = await session.execute(query)

    group_indisp = defaultdict(list)
    for indisp, trip in db_indisp.all():
        if indisp:
            group_indisp[trip.trig].append(
                IndispOut.model_validate(indisp).model_dump()
            )
        else:
            group_indisp[trip.trig] = []

    response = [
        {'trig': trig, 'indisps': indisps}
        for trig, indisps in group_indisp.items()
    ]

    return response


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_indisp(indisp: IndispSchema, session: Session):
    check_date = indisp.date_end < indisp.date_start

    if check_date:
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
    )  # type: ignore

    session.add(new_indisp)  # type: ignore
    await session.commit()

    return {'detail': 'Indisponibilidade adicionada com sucesso'}


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
