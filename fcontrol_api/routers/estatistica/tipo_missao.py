from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import TipoMissao
from fcontrol_api.schemas.estatistica.tipo_missao import (
    TipoMissaoCreate,
    TipoMissaoPublic,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/tipo-missao', tags=['estatistica'])


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[TipoMissaoPublic]],
)
async def list_tipos_missao(session: Session):
    result = await session.scalars(select(TipoMissao).order_by(TipoMissao.cod))
    return success_response(data=list(result.all()))


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[TipoMissaoPublic],
)
async def create_tipo_missao(tipo_missao: TipoMissaoCreate, session: Session):
    existing = await session.scalar(
        select(TipoMissao).where(TipoMissao.cod == tipo_missao.cod)
    )
    if existing:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'Tipo de missao com cod "{tipo_missao.cod}" ja cadastrado',
        )

    new_tipo = TipoMissao(
        cod=tipo_missao.cod,
        desc=tipo_missao.desc,
    )
    session.add(new_tipo)
    await session.commit()
    await session.refresh(new_tipo)

    return success_response(
        data=TipoMissaoPublic.model_validate(new_tipo),
        message='Tipo de missao criado com sucesso',
    )
