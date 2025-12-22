from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.etiquetas import Etiqueta
from fcontrol_api.schemas.etiquetas import EtiquetaSchema

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/etiquetas', tags=['CEGEP'])


@router.get('/', response_model=list[EtiquetaSchema])
async def get_etiquetas(session: Session):
    """Lista todas as etiquetas disponíveis"""
    stmt = select(Etiqueta).order_by(Etiqueta.nome)
    db_etiquetas = (await session.scalars(stmt)).all()
    return db_etiquetas


@router.post('/', response_model=EtiquetaSchema)
async def create_or_update_etiqueta(payload: EtiquetaSchema, session: Session):
    """Cria ou atualiza uma etiqueta"""
    if payload.id:
        # Atualização
        db_etiqueta = await session.scalar(
            select(Etiqueta).where(Etiqueta.id == payload.id)
        )
        if not db_etiqueta:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail='Etiqueta não encontrada',
            )
        db_etiqueta.nome = payload.nome
        db_etiqueta.cor = payload.cor
        db_etiqueta.descricao = payload.descricao
    else:
        # Criação
        db_etiqueta = Etiqueta(
            nome=payload.nome,
            cor=payload.cor,
            descricao=payload.descricao,
        )
        session.add(db_etiqueta)

    await session.commit()
    await session.refresh(db_etiqueta)

    return db_etiqueta


@router.delete('/{etiqueta_id}')
async def delete_etiqueta(etiqueta_id: int, session: Session):
    """Remove uma etiqueta"""
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == etiqueta_id)
    )
    if not db_etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etiqueta não encontrada',
        )

    await session.delete(db_etiqueta)
    await session.commit()

    return {'detail': 'Etiqueta removida com sucesso'}
