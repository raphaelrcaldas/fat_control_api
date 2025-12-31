from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.etiquetas import Etiqueta
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.etiquetas import (
    EtiquetaCreate,
    EtiquetaSchema,
    EtiquetaUpdate,
)
from fcontrol_api.security import get_current_user

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/etiquetas', tags=['etiquetas'])


@router.get('/', response_model=list[EtiquetaSchema])
async def list_etiquetas(session: Session):
    """Lista todas as etiquetas cadastradas"""
    result = await session.execute(select(Etiqueta).order_by(Etiqueta.nome))
    return result.scalars().all()


@router.post(
    '/', response_model=EtiquetaSchema, status_code=HTTPStatus.CREATED
)
async def create_etiqueta(
    etiqueta_data: EtiquetaCreate, session: Session, current_user: CurrentUser
):
    """Cria uma nova etiqueta"""
    etiqueta = Etiqueta(
        nome=etiqueta_data.nome,
        cor=etiqueta_data.cor,
        descricao=etiqueta_data.descricao,
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)
    return etiqueta


@router.put('/{id}', response_model=EtiquetaSchema)
async def update_etiqueta(
    id: int,
    etiqueta_data: EtiquetaUpdate,
    session: Session,
    current_user: CurrentUser,
):
    """Atualiza uma etiqueta existente"""
    etiqueta = await session.get(Etiqueta, id)
    if not etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Etiqueta não encontrada'
        )

    update_data = etiqueta_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(etiqueta, key, value)

    await session.commit()
    await session.refresh(etiqueta)
    return etiqueta


@router.delete('/{id}', status_code=HTTPStatus.OK)
async def delete_etiqueta(
    id: int, session: Session, current_user: CurrentUser
):
    """Remove uma etiqueta"""
    etiqueta = await session.get(Etiqueta, id)
    if not etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Etiqueta não encontrada'
        )

    await session.delete(etiqueta)
    await session.commit()
    return {'detail': 'Etiqueta removida com sucesso'}
