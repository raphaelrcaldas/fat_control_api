from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.schemas.posto_grad import PostoGradSchema

Session = Annotated[AsyncSession, Depends(get_session)]


router = APIRouter(prefix='/postos', tags=['postos'])


@router.get('/', response_model=list[PostoGradSchema])
async def get_postos(session: Session):
    pgs = await session.scalars(select(PostoGrad))

    return pgs.all()
