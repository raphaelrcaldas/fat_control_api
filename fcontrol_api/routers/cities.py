from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.estados_cidades import Cidade

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/cities', tags=['cities'])


@router.get('/')
async def get_cities(search: str, session: Session):
    stmt = select(Cidade).where(Cidade.nome.ilike(f'%{search}%')).limit(20)
    result = await session.scalars(stmt)
    cidades = result.all()

    return cidades
