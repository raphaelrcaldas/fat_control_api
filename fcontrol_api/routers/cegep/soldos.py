from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.posto_grad import PostoGrad, Soldo
from fcontrol_api.schemas.soldo import (
    SoldoCreate,
    SoldoPublic,
    SoldoStats,
    SoldoUpdate,
)

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/soldos', tags=['CEGEP'])


@router.get('/stats', response_model=SoldoStats)
async def get_soldo_stats(
    session: Session,
    circulo: str | None = Query(None, description='Filtrar por circulo'),
):
    """Retorna estatisticas dos soldos"""
    query = select(
        func.count(Soldo.id),
        func.min(Soldo.valor),
        func.max(Soldo.valor),
    )

    if circulo:
        query = query.join(PostoGrad).where(PostoGrad.circulo == circulo)

    result = await session.execute(query)
    row = result.one()

    return SoldoStats(
        total=row[0] or 0,
        min_valor=row[1],
        max_valor=row[2],
    )


@router.get('/', response_model=list[SoldoPublic])
async def list_soldos(
    session: Session,
    circulo: str | None = Query(None, description='Filtrar por circulo'),
    active_only: bool = Query(False, description='Apenas soldos vigentes'),
):
    """Lista todos os soldos com filtros opcionais"""
    query = select(Soldo)

    if circulo:
        query = query.join(PostoGrad).where(PostoGrad.circulo == circulo)

    if active_only:
        today = date.today()
        query = query.where(
            and_(
                Soldo.data_inicio <= today,
                or_(Soldo.data_fim.is_(None), Soldo.data_fim >= today),
            )
        )

    query = query.order_by(Soldo.data_inicio.desc())

    result = await session.scalars(query)
    return result.all()


@router.get('/{soldo_id}', response_model=SoldoPublic)
async def get_soldo(soldo_id: int, session: Session):
    """Busca um soldo por ID"""
    soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    return soldo


@router.post('/', status_code=HTTPStatus.CREATED, response_model=SoldoPublic)
async def create_soldo(soldo: SoldoCreate, session: Session):
    """Cria um novo registro de soldo"""
    if soldo.data_fim and soldo.data_fim <= soldo.data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data inicio',
        )

    posto = await session.scalar(
        select(PostoGrad).where(PostoGrad.short == soldo.pg)
    )

    if not posto:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Posto/Graduacao invalido',
        )

    new_soldo = Soldo(
        pg=soldo.pg,
        data_inicio=soldo.data_inicio,
        data_fim=soldo.data_fim,
        valor=soldo.valor,
    )

    session.add(new_soldo)
    await session.commit()
    await session.refresh(new_soldo)

    return new_soldo


@router.put('/{soldo_id}', response_model=SoldoPublic)
async def update_soldo(soldo_id: int, soldo: SoldoUpdate, session: Session):
    """Atualiza um soldo existente"""
    db_soldo = await session.scalar(
        select(Soldo).where(Soldo.id == soldo_id)
    )

    if not db_soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    update_data = soldo.model_dump(exclude_unset=True)

    # Valida datas
    data_inicio = update_data.get('data_inicio', db_soldo.data_inicio)
    data_fim = update_data.get('data_fim', db_soldo.data_fim)
    if data_fim and data_fim <= data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data inicio',
        )

    if 'pg' in update_data:
        posto = await session.scalar(
            select(PostoGrad).where(PostoGrad.short == update_data['pg'])
        )
        if not posto:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Posto/Graduacao invalido',
            )

    for key, value in update_data.items():
        setattr(db_soldo, key, value)

    await session.commit()
    await session.refresh(db_soldo)

    return db_soldo


@router.delete('/{soldo_id}')
async def delete_soldo(soldo_id: int, session: Session):
    """Deleta um registro de soldo"""
    db_soldo = await session.scalar(
        select(Soldo).where(Soldo.id == soldo_id)
    )

    if not db_soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    await session.delete(db_soldo)
    await session.commit()

    return {'detail': 'Soldo deletado com sucesso'}
