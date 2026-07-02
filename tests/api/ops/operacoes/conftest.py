"""Fixtures do módulo Operações.

Tokens com conjuntos de permissão específicos para exercitar cada gate do
router (`operacoes.view` / `operacoes.create` / `operacoes.delete`)
separadamente, sem depender do bypass de admin. Todas as roles são
vinculadas à org ativa '11gt'.
"""

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)


async def _ensure_perm(session, resource, action):
    res = await session.scalar(
        select(Resources).where(Resources.name == resource)
    )
    if res is None:
        res = Resources(name=resource, description=resource)
        session.add(res)
        await session.flush()
    perm = await session.scalar(
        select(Permissions).where(
            Permissions.resource_id == res.id, Permissions.name == action
        )
    )
    if perm is None:
        perm = Permissions(resource_id=res.id, name=action, description=action)
        session.add(perm)
        await session.flush()
    return perm


@pytest.fixture
def make_perm_token(users, session, make_org_token):
    """Cunha um token de role não-admin com os grants informados.

    `perms` é uma lista de tuplas (resource, action). A role é vinculada ao
    primeiro user na org '11gt' (ou outra via `org`).
    """

    async def _make(perms, *, org='11gt', role_name='oper_role'):
        user, _ = users
        role = Roles(name=role_name, description=role_name)
        session.add(role)
        await session.flush()
        for resource, action in perms:
            perm = await _ensure_perm(session, resource, action)
            session.add(
                RolePermissions(role_id=role.id, permission_id=perm.id)
            )
        session.add(
            UserRole(user_id=user.id, role_id=role.id, organizacao_id=org)
        )
        await session.commit()
        return await make_org_token(user)

    return _make


@pytest.fixture
async def oper_viewer_token(make_perm_token):
    """Só lê operações (operacoes.view), sem criar/excluir."""
    return await make_perm_token(
        [('operacoes', 'view')], role_name='oper_viewer'
    )


@pytest.fixture
async def oper_writer_token(make_perm_token):
    """Lê e escreve (view + create), mas NÃO exclui (sem operacoes.delete)."""
    return await make_perm_token(
        [('operacoes', 'view'), ('operacoes', 'create')],
        role_name='oper_writer',
    )
