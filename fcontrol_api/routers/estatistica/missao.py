from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import Etapa, Missao
from fcontrol_api.schemas.estatistica.etapa import (
    MissaoCreate,
    MissaoPublic,
    MissaoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
MissaoId = Annotated[int, Path()]

router = APIRouter(prefix='/missao', tags=['estatistica'])


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[MissaoPublic],
)
async def create_missao(
    missao: MissaoCreate, session: Session,
) -> ApiResponse[MissaoPublic]:
    new_missao = Missao(
        titulo=missao.titulo,
        obs=missao.obs,
        is_simulador=missao.is_simulador,
    )
    session.add(new_missao)
    await session.commit()
    await session.refresh(new_missao)

    return success_response(
        data=MissaoPublic.model_validate(new_missao),
        message='Missao criada com sucesso',
    )


@router.put(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoPublic],
)
async def update_missao(
    missao_id: MissaoId,
    missao_data: MissaoUpdate,
    session: Session,
) -> ApiResponse[MissaoPublic]:
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    if missao_data.titulo is not None:
        missao.titulo = missao_data.titulo
    if missao_data.obs is not None:
        missao.obs = missao_data.obs

    await session.commit()
    await session.refresh(missao)

    return success_response(
        data=MissaoPublic.model_validate(missao),
        message='Missao atualizada com sucesso',
    )


@router.delete(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_missao(
    missao_id: MissaoId, session: Session,
) -> ApiResponse[None]:
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    has_etapas = await session.scalar(
        select(Etapa.id).where(Etapa.missao_id == missao_id).limit(1)
    )
    if has_etapas:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Nao e possivel excluir missao com etapas vinculadas',
        )

    await session.delete(missao)
    await session.commit()

    return success_response(
        message='Missao excluida com sucesso',
    )
