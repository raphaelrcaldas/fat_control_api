from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.inteligencia.passaportes import Passaporte
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.inteligencia.passaportes import (
    PassaportePublic,
    PassaporteUpdate,
    TripPassaporteOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/passaportes', tags=['Inteligencia'])


@router.get(
    '/',
    response_model=ApiResponse[list[TripPassaporteOut]],
)
async def list_passaportes(
    session: Session,
    p_g: Annotated[str | None, Query()] = None,
    funcao: Annotated[str | None, Query()] = None,
):
    """Lista tripulantes ativos com seus passaportes."""
    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.id.label('user_id'),
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            User.saram,
            Passaporte.id.label('passaporte_id'),
            Passaporte.passaporte.label('passaporte_num'),
            Passaporte.validade_passaporte,
            Passaporte.validade_visa,
        )
        .select_from(Tripulante)
        .join(User, User.id == Tripulante.user_id)
        .join(PostoGrad, PostoGrad.short == User.p_g)
        .outerjoin(
            Passaporte,
            Passaporte.user_id == User.id,
        )
        .where(Tripulante.active.is_(True))
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
            User.id,
        )
    )

    if p_g:
        pgs = [p.strip() for p in p_g.split(',')]
        query = query.where(User.p_g.in_(pgs))

    if funcao:
        funcs = [f.strip() for f in funcao.split(',')]
        query = (
            query
            .join(Funcao, Funcao.trip_id == Tripulante.id)
            .where(Funcao.func.in_(funcs))
            .distinct()
        )

    rows = await session.execute(query)
    items = [
        TripPassaporteOut(
            trip_id=r.trip_id,
            user_id=r.user_id,
            p_g=r.p_g,
            nome_guerra=r.nome_guerra,
            nome_completo=r.nome_completo,
            saram=r.saram,
            passaporte=PassaportePublic(
                id=r.passaporte_id,
                user_id=r.user_id,
                passaporte=r.passaporte_num,
                validade_passaporte=r.validade_passaporte,
                validade_visa=r.validade_visa,
            )
            if r.passaporte_id is not None
            else None,
        )
        for r in rows.all()
    ]

    return success_response(data=items)


@router.put(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def upsert_passaporte(
    trip_id: int,
    session: Session,
    dados: PassaporteUpdate,
):
    """Cria ou atualiza passaporte de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == tripulante.user_id)
    )

    if passaporte:
        for key, value in dados.model_dump(exclude_unset=True).items():
            setattr(passaporte, key, value)
        message = 'Passaporte atualizado com sucesso'
    else:
        passaporte = Passaporte(
            user_id=tripulante.user_id,
            passaporte=dados.passaporte,
            validade_passaporte=dados.validade_passaporte,
            validade_visa=dados.validade_visa,
        )
        session.add(passaporte)
        message = 'Passaporte cadastrado com sucesso'

    await session.commit()

    return success_response(message=message)


@router.delete(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def delete_passaporte(
    trip_id: int,
    session: Session,
):
    """Remove passaporte de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    passaporte = await session.scalar(
        select(Passaporte).where(Passaporte.user_id == tripulante.user_id)
    )
    if not passaporte:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Passaporte nao encontrado',
        )

    await session.delete(passaporte)
    await session.commit()

    return success_response(message='Passaporte removido com sucesso')
