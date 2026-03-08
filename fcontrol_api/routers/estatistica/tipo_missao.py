from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import (
    OIEtapa,
    TipoMissao,
)
from fcontrol_api.schemas.estatistica.tipo_missao import (
    TipoMissaoCreate,
    TipoMissaoPublic,
    TipoMissaoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
TipoMissaoId = Annotated[int, Path()]

router = APIRouter(
    prefix='/tipo-missao', tags=['estatistica']
)


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


@router.put(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[TipoMissaoPublic],
)
async def update_tipo_missao(
    id: TipoMissaoId,
    data: TipoMissaoUpdate,
    session: Session,
) -> ApiResponse[TipoMissaoPublic]:
    tipo = await session.scalar(
        select(TipoMissao).where(TipoMissao.id == id)
    )
    if not tipo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tipo de missao nao encontrado',
        )

    updates = data.model_dump(exclude_unset=True)
    if 'cod' in updates and updates['cod'] is not None:
        existing = await session.scalar(
            select(TipoMissao).where(
                TipoMissao.cod == updates['cod'],
                TipoMissao.id != id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=(
                    f'Tipo de missao com cod '
                    f'"{updates["cod"]}" ja cadastrado'
                ),
            )

    for campo, valor in updates.items():
        setattr(tipo, campo, valor)

    await session.commit()
    await session.refresh(tipo)
    return success_response(
        data=TipoMissaoPublic.model_validate(tipo),
        message='Tipo de missao atualizado',
    )


@router.delete(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_tipo_missao(
    id: TipoMissaoId,
    session: Session,
) -> ApiResponse[None]:
    tipo = await session.scalar(
        select(TipoMissao).where(TipoMissao.id == id)
    )
    if not tipo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tipo de missao nao encontrado',
        )

    in_use = await session.scalar(
        select(OIEtapa.id)
        .where(OIEtapa.tipo_missao_id == id)
        .limit(1)
    )
    if in_use:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Tipo de missao em uso por etapas, '
                'nao pode ser removido'
            ),
        )

    await session.delete(tipo)
    await session.commit()
    return success_response(
        message='Tipo de missao removido',
    )
