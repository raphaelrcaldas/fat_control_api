from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import Resources
from fcontrol_api.schemas.security import ResourceSchema

router = APIRouter(prefix='/resources')

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/', response_model=list[ResourceSchema])
async def list_resources(session: Session):
    stmt = select(Resources).order_by(Resources.name)
    resources = await session.scalars(stmt)
    return list(resources)
