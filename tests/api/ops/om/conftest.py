import pytest

from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.models.shared.aeronaves import Aeronave


@pytest.fixture(autouse=True)
async def seed_aeronaves(session):
    """Cria aeronaves necessárias para FK de matricula_anv."""
    aeros = [
        Aeronave(
            matricula='2850',
            active=True,
            sit='DI',
            obs=None,
        ),
        Aeronave(
            matricula='2851',
            active=True,
            sit='DI',
            obs=None,
        ),
        Aeronave(
            matricula='2852',
            active=True,
            sit='DI',
            obs=None,
        ),
    ]
    session.add_all(aeros)
    await session.commit()


@pytest.fixture
async def om_editor_token(users, session, make_org_token):
    """Token de editor de OM: pode criar/editar, mas não transitar status.

    Monta uma role não-admin vinculada à '11gt' com os grants
    `ordem_missao.create` e `ordem_missao.update`, deliberadamente sem
    `ordem_missao.status.update`. Serve para provar que `update_ordem`
    aplica o gate granular de status (aprovar/cancelar) além do
    `ordem_missao.update` herdado pelo `Depends`.
    """
    user, _ = users

    res_om = Resources(name='ordem_missao', description='OM')
    res_status = Resources(name='ordem_missao.status', description='OM status')
    session.add_all([res_om, res_status])
    await session.flush()

    perm_create = Permissions(
        resource_id=res_om.id, name='create', description='criar OM'
    )
    perm_update = Permissions(
        resource_id=res_om.id, name='update', description='editar OM'
    )
    # Existe no banco, mas NÃO é concedida a esta role de propósito.
    perm_status = Permissions(
        resource_id=res_status.id, name='update', description='status OM'
    )
    session.add_all([perm_create, perm_update, perm_status])
    await session.flush()

    role = Roles(name='om_editor', description='Editor de OM sem status')
    session.add(role)
    await session.flush()

    session.add_all([
        RolePermissions(role_id=role.id, permission_id=perm_create.id),
        RolePermissions(role_id=role.id, permission_id=perm_update.id),
    ])
    session.add(
        UserRole(user_id=user.id, role_id=role.id, organizacao_id='11gt')
    )
    await session.commit()

    return await make_org_token(user)
