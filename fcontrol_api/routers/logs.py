from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.schemas.logs import UserActionLogOut

router = APIRouter(prefix='/logs', tags=['Logs'])


@router.get('/user-actions', response_model=list[UserActionLogOut])
async def listar_logs(
    session: AsyncSession = Depends(get_session),
    user_id: int | None = None,
    resource: str | None = None,
    resource_id: int | None = None,
    action: str | None = None,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
):
    query = select(UserActionLog).options(selectinload(UserActionLog.user))

    filters = []

    if user_id:
        filters.append(UserActionLog.user_id == user_id)
    if resource:
        filters.append(UserActionLog.resource == resource)
    if resource_id:
        filters.append(UserActionLog.resource_id == resource_id)
    if action:
        filters.append(UserActionLog.action == action)
    if start:
        filters.append(UserActionLog.timestamp >= start)
    if end:
        filters.append(UserActionLog.timestamp <= end)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(UserActionLog.timestamp.desc())

    result = await session.scalars(query)
    return result.all()
