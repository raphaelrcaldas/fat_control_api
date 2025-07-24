from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.resources import Permissions, UserRole

Session = Annotated[AsyncSession, Depends(get_session)]


async def get_user_roles(user_id: int, session: Session):
    result = await session.scalar(
        select(UserRole).where(UserRole.user_id == user_id)
    )

    role_data = None

    if result:
        user_role = result.role

        perms: list[Permissions] = [
            perm.permission for perm in (user_role.permissions)
        ]
        perms = [
            {'resource': perm.resource.name, 'name': perm.name}
            for perm in perms
        ]

        role_data = {'role': user_role.name, 'perms': perms}

    return role_data


async def token_data(user: User, session: Session):
    data = {
        'sub': f'{user.posto.short} {user.nome_guerra}',
        'user_id': user.id,
        'role': await get_user_roles(user.id, session),
    }

    if user.first_login:
        data['first_login'] = True

    return data
