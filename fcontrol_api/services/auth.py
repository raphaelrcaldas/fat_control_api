from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import (
    Permissions,
    RolePermissions,
    Roles,
    UserRole,
)

Session = Annotated[AsyncSession, Depends(get_session)]


async def get_user_roles(user_id: int, session: Session):
    role_data = {'role': None, 'perms': []}

    query = (
        select(UserRole)
        .where(UserRole.user_id == user_id)
        .options(
            joinedload(UserRole.role)
            .joinedload(Roles.permissions)
            .joinedload(RolePermissions.permission)
            .joinedload(Permissions.resource)
        )
    )

    result = await session.scalar(query)
    if not result:
        return role_data

    user_role = result.role
    perms = [
        {
            'resource': perm.permission.resource.name,
            'name': perm.permission.name,
        }
        for perm in user_role.permissions
    ]

    role_data['role'] = user_role.name
    role_data['perms'] = perms

    return role_data
