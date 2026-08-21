"""Fixtures específicas para testes de usuários.

Cada fixture `user_with_<x>_permission` devolve o primeiro usuário da fixture
`users` com a permissão `user:<x>` — e **só ela**.

Duas sutilezas que tornam esse setup não-óbvio:

- A role usada é a `user` (não-admin). Com a role `admin` o gate passaria por
  *bypass*, e o teste validaria o bypass em vez da permissão que diz testar.
- O vínculo é escopado à org '11gt'. O `permission_checker` resolve a role
  pela org ativa (`organizacao_id IS NOT DISTINCT FROM active_org`), então um
  vínculo de Sistema (org NULL) não concederia nada sob um token com
  `active_org='11gt'`.
"""

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)

ORG = '11gt'


async def _grant_user_permission(session, user, action: str):
    """Concede `user:<action>` ao usuário via role não-admin na org '11gt'."""
    role = await session.scalar(select(Roles).where(Roles.name == 'user'))

    resource = await session.scalar(
        select(Resources).where(Resources.name == 'users')
    )
    if not resource:
        resource = Resources(name='users', description='User resource')
        session.add(resource)
        await session.flush()

    permission = await session.scalar(
        select(Permissions).where(
            Permissions.resource_id == resource.id,
            Permissions.name == action,
        )
    )
    if not permission:
        permission = Permissions(
            resource_id=resource.id,
            name=action,
            description=f'{action} users',
        )
        session.add(permission)
        await session.flush()

    role_perm = await session.scalar(
        select(RolePermissions).where(
            RolePermissions.role_id == role.id,
            RolePermissions.permission_id == permission.id,
        )
    )
    if not role_perm:
        session.add(
            RolePermissions(role_id=role.id, permission_id=permission.id)
        )

    user_role = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.organizacao_id == ORG,
        )
    )
    if not user_role:
        session.add(
            UserRole(user_id=user.id, role_id=role.id, organizacao_id=ORG)
        )

    await session.commit()
    await session.refresh(user)

    return user


@pytest.fixture
async def user_with_create_permission(session, users):
    """Primeiro usuário com a permissão 'user:create' (e nenhuma outra)."""
    user, _ = users
    return await _grant_user_permission(session, user, 'create')


@pytest.fixture
async def user_with_update_permission(session, users):
    """Primeiro usuário com a permissão 'user:update' (e nenhuma outra)."""
    user, _ = users
    return await _grant_user_permission(session, user, 'update')


@pytest.fixture
async def user_with_delete_permission(session, users):
    """Primeiro usuário com a permissão 'user:delete' (e nenhuma outra)."""
    user, _ = users
    return await _grant_user_permission(session, user, 'delete')


@pytest.fixture
async def user_with_view_permission(session, users):
    """Primeiro usuário com a permissão 'user:view' (e nenhuma outra)."""
    user, _ = users
    return await _grant_user_permission(session, user, 'view')
