import json

from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.security.logs import UserActionLog


async def log_user_action(
    session: AsyncSession,
    user_id: int,
    action: str,
    resource: str,
    resource_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
):
    log = UserActionLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        before=json.dumps(before) if before else None,
        after=json.dumps(after) if after else None,
    )
    session.add(log)
