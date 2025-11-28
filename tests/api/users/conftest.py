"""
Fixtures específicas para testes de usuários.
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


@pytest.fixture
async def user_with_create_permission(session, users):
    """
    Cria um usuário com permissão de criar outros usuários.

    Retorna o primeiro usuário da fixture 'users' com a permissão
    'user:create' atribuída através de uma role.
    """
    user, _ = users

    # Busca ou cria a role 'admin'
    admin_role = await session.scalar(
        select(Roles).where(Roles.name == 'admin')
    )
    if not admin_role:
        admin_role = Roles(name='admin', description='Administrator')
        session.add(admin_role)
        await session.flush()

    # Busca ou cria o recurso 'user'
    user_resource = await session.scalar(
        select(Resources).where(Resources.name == 'user')
    )
    if not user_resource:
        user_resource = Resources(name='user', description='User resource')
        session.add(user_resource)
        await session.flush()

    # Busca ou cria a permissão 'create' no recurso 'user'
    create_permission = await session.scalar(
        select(Permissions).where(
            Permissions.resource_id == user_resource.id,
            Permissions.name == 'create',
        )
    )
    if not create_permission:
        create_permission = Permissions(
            resource_id=user_resource.id,
            name='create',
            description='Create users',
        )
        session.add(create_permission)
        await session.flush()

    # Associa permissão à role (se ainda não existe)
    role_perm = await session.scalar(
        select(RolePermissions).where(
            RolePermissions.role_id == admin_role.id,
            RolePermissions.permission_id == create_permission.id,
        )
    )
    if not role_perm:
        role_perm = RolePermissions(
            role_id=admin_role.id,
            permission_id=create_permission.id,
        )
        session.add(role_perm)

    # Associa role ao usuário (se ainda não existe)
    user_role = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == admin_role.id,
        )
    )
    if not user_role:
        user_role = UserRole(user_id=user.id, role_id=admin_role.id)
        session.add(user_role)

    await session.commit()
    await session.refresh(user)

    return user


@pytest.fixture
async def user_with_update_permission(session, users):
    """
    Cria um usuário com permissão de atualizar outros usuários.

    Retorna o primeiro usuário da fixture 'users' com a permissão
    'user:update' atribuída através de uma role.
    """
    user, _ = users

    # Busca ou cria a role 'admin'
    admin_role = await session.scalar(
        select(Roles).where(Roles.name == 'admin')
    )
    if not admin_role:
        admin_role = Roles(name='admin', description='Administrator')
        session.add(admin_role)
        await session.flush()

    # Busca ou cria o recurso 'user'
    user_resource = await session.scalar(
        select(Resources).where(Resources.name == 'user')
    )
    if not user_resource:
        user_resource = Resources(name='user', description='User resource')
        session.add(user_resource)
        await session.flush()

    # Busca ou cria a permissão 'update' no recurso 'user'
    update_permission = await session.scalar(
        select(Permissions).where(
            Permissions.resource_id == user_resource.id,
            Permissions.name == 'update',
        )
    )
    if not update_permission:
        update_permission = Permissions(
            resource_id=user_resource.id,
            name='update',
            description='Update users',
        )
        session.add(update_permission)
        await session.flush()

    # Associa permissão à role (se ainda não existe)
    role_perm = await session.scalar(
        select(RolePermissions).where(
            RolePermissions.role_id == admin_role.id,
            RolePermissions.permission_id == update_permission.id,
        )
    )
    if not role_perm:
        role_perm = RolePermissions(
            role_id=admin_role.id,
            permission_id=update_permission.id,
        )
        session.add(role_perm)

    # Associa role ao usuário (se ainda não existe)
    user_role = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == admin_role.id,
        )
    )
    if not user_role:
        user_role = UserRole(user_id=user.id, role_id=admin_role.id)
        session.add(user_role)

    await session.commit()
    await session.refresh(user)

    return user
