from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.estados_cidades import Cidade
from fcontrol_api.schemas.cidade import CidadeSchema
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/cities', tags=['cities'])


@router.get('/', response_model=ApiResponse[list[CidadeSchema]])
async def get_cities(search: str, session: Session):
    stmt = select(Cidade).where(Cidade.nome.ilike(f'%{search}%')).limit(20)
    result = await session.scalars(stmt)
    cidades = result.all()

    return success_response(
        data=[CidadeSchema.model_validate(c) for c in cidades]
    )
