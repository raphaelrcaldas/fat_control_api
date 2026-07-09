from datetime import datetime, time
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.logs import UserActionLogOut
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrgOptional,
    ensure_org_permission_or_owner,
    get_current_user,
    is_system_admin,
    require_system_admin,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/logs', tags=['Logs'])


@router.get(
    '/user-actions',
    response_model=ApiResponse[list[UserActionLogOut]],
)
async def listar_logs(
    session: Session,
    active_org: ActiveOrgOptional,
    current_user: CurrentUser,
    user_id: int | None = None,
    resource: str | None = None,
    resource_id: int | None = None,
    action: str | None = None,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
):
    # Acesso em camadas (o log expõe atores de todas as orgs):
    # 1. Próprios logs (home: "último acesso") — qualquer usuário.
    # 2. Admin de sistema — listagem global (tela admin/logs).
    # 3. Auditoria de um usuário (aba histórico) — exige user.view na
    #    org ativa e alvo dentro da org, mesma lente do GET /users/{id}.
    if user_id == current_user.id:
        pass
    elif await is_system_admin(current_user.id, session, active_org):
        pass
    elif resource == 'user' and resource_id is not None:
        if resource_id != current_user.id:
            target = await session.scalar(
                select(User).where(User.id == resource_id)
            )
            if (
                target
                and active_org is not None
                and target.unidade != active_org
            ):
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail='Usuario nao encontrado',
                )
        await ensure_org_permission_or_owner(
            current_user, session, active_org, 'user', 'view', resource_id
        )
    else:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail='SCOPE_FORBIDDEN'
        )

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
        filters.append(
            UserActionLog.timestamp >= datetime.combine(start, time(0, 0, 0))
        )
    if end:
        filters.append(
            UserActionLog.timestamp <= datetime.combine(end, time(23, 59, 59))
        )

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(UserActionLog.timestamp.desc()).limit(25)

    result = await session.scalars(query)
    return success_response(data=list(result.all()))


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
