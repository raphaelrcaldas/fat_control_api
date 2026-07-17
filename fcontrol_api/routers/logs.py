from datetime import datetime, time
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.logs import UserActionLogOut
from fcontrol_api.schemas.response import ApiPaginatedResponse, ApiResponse
from fcontrol_api.security import require_system_admin
from fcontrol_api.utils.responses import paginated_response, success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/logs', tags=['Logs'])


@router.get(
    '/user-actions',
    response_model=ApiPaginatedResponse[UserActionLogOut],
)
async def listar_logs(
    session: Session,
    user_id: int | None = None,
    resource: str | None = None,
    resource_id: int | None = None,
    action: str | None = None,
    search: str | None = None,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 25,
):
    query = select(UserActionLog).options(selectinload(UserActionLog.user))
    count_query = select(func.count()).select_from(UserActionLog)

    if search:
        # Busca pelo autor da ação (nome de guerra OU nome completo)
        query = query.join(UserActionLog.user)
        count_query = count_query.join(UserActionLog.user)

    filters = []

    if user_id:
        filters.append(UserActionLog.user_id == user_id)
    if resource:
        filters.append(UserActionLog.resource == resource)
    if resource_id:
        filters.append(UserActionLog.resource_id == resource_id)
    if action:
        filters.append(UserActionLog.action == action)
    if search:
        search_term = f'%{search.strip()}%'
        filters.append(
            or_(
                User.nome_guerra.ilike(search_term),
                User.nome_completo.ilike(search_term),
            )
        )
    if start:
        filters.append(
            UserActionLog.timestamp >= datetime.combine(start, time(0, 0, 0))
        )
    if end:
        filters.append(
            UserActionLog.timestamp <= datetime.combine(end, time(23, 59, 59))
        )

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    query = (
        query.order_by(
            UserActionLog.timestamp.desc(),
            UserActionLog.id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    total = await session.scalar(count_query) or 0
    result = await session.scalars(query)

    return paginated_response(
        items=list(result.all()),
        total=total,
        page=page,
        per_page=per_page,
    )


@router.delete(
    '/user-actions/{log_id}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_system_admin)],
)
async def excluir_log(
    log_id: int,
    session: AsyncSession = Depends(get_session),
):
    log = await session.get(UserActionLog, log_id)

    if not log:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Log não encontrado',
        )

    await session.delete(log)
    await session.commit()

    return success_response(message='Log excluído com sucesso')
