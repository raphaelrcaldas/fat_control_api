from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.schemas.posto_grad import PostoGradSchema
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]


router = APIRouter(prefix='/postos', tags=['postos'])


@router.get('/', response_model=ApiResponse[list[PostoGradSchema]])
async def get_postos(session: Session):
    pgs = await session.scalars(select(PostoGrad))

    return success_response(data=list(pgs.all()))
