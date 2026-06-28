"""Fixtures dos testes de endpoint do control-plane RBAC (`/security`).

Tokens por escopo de admin (ver gating em `routers/security/__init__.py`):

- `sysadmin_token`: admin de SISTEMA — vínculo admin (role 1) com
  `organizacao_id NULL` e token SEM `active_org`. Satisfaz
  `require_system_admin` (rotas de permissions/resources e grants
  role→permissão) e também `require_admin`.
- `unit_admin_token`: admin de UNIDADE '11gt' — passa em `require_admin`,
  mas toma 403 em `require_system_admin` (active_org preenchido).
- `nonadmin_token`: usuário autenticado com role 'user' (não-admin) na org
  ativa '11gt' — toma 403 já em `require_admin`.
"""

import pytest
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.shared.users import User
from fcontrol_api.security import create_access_token


async def _token_for(session, user, active_org=None):
    db_user = await session.scalar(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.posto))
    )
    data = {
        'sub': f'{db_user.posto.short} {db_user.nome_guerra}',
        'user_id': db_user.id,
        'app_client': 'test-client',
    }
    if active_org is not None:
        data['active_org'] = active_org
    return create_access_token(data=data)


async def _bind_role(session, user_id, role_id, org=None):
    existing = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.organizacao_id.is_not_distinct_from(org),
        )
    )
    if existing:
        existing.role_id = role_id
    else:
        session.add(
            UserRole(user_id=user_id, role_id=role_id, organizacao_id=org)
        )
    await session.commit()


@pytest.fixture
async def sysadmin_token(token):
    """`token` já é admin de sistema (role 1 org NULL, sem active_org)."""
    return token


@pytest.fixture
async def unit_admin_token(org_admin_token):
    """Admin de unidade '11gt' (require_admin ok; require_system_admin 403)."""
    return org_admin_token


@pytest.fixture
async def nonadmin_token(users, session):
    """Usuário autenticado, role 'user' (não-admin) na org ativa '11gt'."""
    _, other = users
    await _bind_role(session, other.id, role_id=2, org='11gt')
    return await _token_for(session, other, active_org='11gt')
