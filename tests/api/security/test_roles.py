"""Testes de endpoint do RBAC de perfis (`/security/roles`).

Cobre as três camadas de gating e as regras de escopo:

- leitura/escrita de vínculos user↔role: `require_admin` (admin na org
  ativa) + `_ensure_org_in_scope` (admin de unidade só opera a própria org);
- grants role↔permissão: `require_system_admin` (admin de sistema);
- anti-escalonamento: admin de unidade não cria vínculo de sistema (org
  NULL) nem de outra org; admin não remove o próprio acesso.

Seeds de role: 1=admin, 2=user, 3=viewer. Tenants: '11gt' e '1gt'.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    UserRole,
)

pytestmark = pytest.mark.anyio


async def _bind(session, user_id, role_id, org):
    session.add(UserRole(user_id=user_id, role_id=role_id, organizacao_id=org))
    await session.commit()


async def _new_permission(session, name='view'):
    resource = Resources(name='rec_grant', description='desc')
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    perm = Permissions(resource_id=resource.id, name=name, description='desc')
    session.add(perm)
    await session.commit()
    await session.refresh(perm)
    return perm


# --- Leitura -------------------------------------------------------------- #


async def test_list_roles_as_unit_admin_ok(client, unit_admin_token):
    response = await client.get(
        '/security/roles/',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    nomes = {r['name'] for r in response.json()['data']}
    assert {'admin', 'user', 'viewer'} <= nomes


async def test_list_roles_forbidden_for_nonadmin(client, nonadmin_token):
    response = await client.get(
        '/security/roles/',
        headers={'Authorization': f'Bearer {nonadmin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_roles_requires_token(client):
    response = await client.get('/security/roles/')
    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_get_role_detail_ok(client, unit_admin_token):
    response = await client.get(
        '/security/roles/1',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['name'] == 'admin'
    assert isinstance(data['permissions'], list)


async def test_get_role_detail_not_found(client, unit_admin_token):
    response = await client.get(
        '/security/roles/999999',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Perfil não encontrado'


async def test_list_users_roles_scoped_to_active_org(
    client, session, users, unit_admin_token
):
    """Admin de '11gt' não enxerga vínculos de outra org."""
    _, other = users
    await _bind(session, other.id, role_id=2, org='1gt')

    response = await client.get(
        '/security/roles/users/',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    items = response.json()['data']
    # Tudo que volta é da org ativa '11gt' (o vínculo de '1gt' não vaza).
    assert all(it['organizacao_id'] == '11gt' for it in items)


# --- add_user_role -------------------------------------------------------- #


async def test_add_user_role_ok(client, session, users, unit_admin_token):
    _, other = users
    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Perfil cadastrado com sucesso'

    ur = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == other.id,
            UserRole.organizacao_id == '11gt',
        )
    )
    assert ur is not None
    assert ur.role_id == 2


async def test_add_user_role_cross_org_forbidden(
    client, users, unit_admin_token
):
    """Admin de '11gt' não cria vínculo em '1gt'."""
    _, other = users
    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '1gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    msg = response.json()['message']
    assert msg == 'Operação fora do escopo da sua organização'


async def test_add_user_role_system_scope_forbidden_for_unit_admin(
    client, users, unit_admin_token
):
    """Admin de unidade não cria vínculo de sistema (org NULL)."""
    _, other = users
    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 1, 'organizacao_id': None},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_add_user_role_user_not_found(client, unit_admin_token):
    response = await client.post(
        '/security/roles/users/',
        json={'user_id': 999999, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Usuário não encontrado'


async def test_add_user_role_role_not_found(client, users, unit_admin_token):
    _, other = users
    response = await client.post(
        '/security/roles/users/',
        json={
            'user_id': other.id,
            'role_id': 999999,
            'organizacao_id': '11gt',
        },
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Perfil não encontrado'


async def test_add_user_role_invalid_tenant(client, users, sysadmin_token):
    """Org inexistente como tenant → 404 (via admin de sistema)."""
    _, other = users
    response = await client.post(
        '/security/roles/users/',
        json={
            'user_id': other.id,
            'role_id': 2,
            'organizacao_id': 'zztest',
        },
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    msg = response.json()['message']
    assert msg == 'Organização não é um tenant da plataforma'


async def test_add_user_role_system_scope_non_admin_role_422(
    client, users, sysadmin_token
):
    """Só a role 'admin' pode ser de sistema (org NULL)."""
    _, other = users
    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': None},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_add_user_role_duplicate_conflict(
    client, session, users, unit_admin_token
):
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')
    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.CONFLICT
    msg = response.json()['message']
    assert msg == 'Usuário já possui um perfil nessa organização'


# --- update_user_role ----------------------------------------------------- #


async def test_update_user_role_ok(client, session, users, unit_admin_token):
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')
    response = await client.put(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Perfil atualizado com sucesso'

    ur = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == other.id,
            UserRole.organizacao_id == '11gt',
        )
    )
    assert ur.role_id == 3


async def test_update_user_role_not_found(client, users, unit_admin_token):
    _, other = users
    response = await client.put(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_user_role_cross_org_forbidden(
    client, users, unit_admin_token
):
    _, other = users
    response = await client.put(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '1gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


# --- delete_user_role ----------------------------------------------------- #


async def test_delete_user_role_ok(client, session, users, unit_admin_token):
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')
    response = await client.request(
        'DELETE',
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Perfil deletado com sucesso'

    ur = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == other.id,
            UserRole.organizacao_id == '11gt',
        )
    )
    assert ur is None


async def test_delete_user_role_self_forbidden(
    client, users, unit_admin_token
):
    """Admin não pode remover o próprio acesso."""
    user, _ = users
    response = await client.request(
        'DELETE',
        '/security/roles/users/',
        json={'user_id': user.id, 'role_id': 1, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    msg = response.json()['message']
    assert msg == 'Você não pode remover o próprio acesso'


async def test_delete_user_role_role_mismatch(
    client, session, users, unit_admin_token
):
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')
    response = await client.request(
        'DELETE',
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()['message'] == 'Roles não conferem'


async def test_delete_user_role_not_found(client, users, unit_admin_token):
    _, other = users
    response = await client.request(
        'DELETE',
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


# --- grants role↔permissão (system admin) --------------------------------- #


async def test_add_permission_to_role_ok(client, session, sysadmin_token):
    perm = await _new_permission(session)
    response = await client.post(
        '/security/roles/2/permissions/',
        json={'permission_id': perm.id},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.CREATED
    msg = response.json()['message']
    assert msg == 'Permissão adicionada ao perfil com sucesso'

    rp = await session.scalar(
        select(RolePermissions).where(
            RolePermissions.role_id == 2,
            RolePermissions.permission_id == perm.id,
        )
    )
    assert rp is not None


async def test_add_permission_to_role_forbidden_for_unit_admin(
    client, session, unit_admin_token
):
    perm = await _new_permission(session)
    response = await client.post(
        '/security/roles/2/permissions/',
        json={'permission_id': perm.id},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_add_permission_to_role_forbidden_for_nonadmin(
    client, session, nonadmin_token
):
    perm = await _new_permission(session)
    response = await client.post(
        '/security/roles/2/permissions/',
        json={'permission_id': perm.id},
        headers={'Authorization': f'Bearer {nonadmin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_add_permission_to_role_role_not_found(
    client, session, sysadmin_token
):
    perm = await _new_permission(session)
    response = await client.post(
        '/security/roles/999999/permissions/',
        json={'permission_id': perm.id},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Perfil não encontrado'


async def test_add_permission_to_role_permission_not_found(
    client, sysadmin_token
):
    response = await client.post(
        '/security/roles/2/permissions/',
        json={'permission_id': 999999},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Permissão não encontrada'


async def test_add_permission_to_role_duplicate_conflict(
    client, session, sysadmin_token
):
    perm = await _new_permission(session)
    session.add(RolePermissions(role_id=2, permission_id=perm.id))
    await session.commit()

    response = await client.post(
        '/security/roles/2/permissions/',
        json={'permission_id': perm.id},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()['message'] == 'Perfil já possui esta permissão'


async def test_remove_permission_from_role_ok(client, session, sysadmin_token):
    perm = await _new_permission(session)
    session.add(RolePermissions(role_id=2, permission_id=perm.id))
    await session.commit()

    response = await client.delete(
        f'/security/roles/2/permissions/{perm.id}',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    msg = response.json()['message']
    assert msg == 'Permissão removida do perfil com sucesso'

    rp = await session.scalar(
        select(RolePermissions).where(
            RolePermissions.role_id == 2,
            RolePermissions.permission_id == perm.id,
        )
    )
    assert rp is None


async def test_remove_permission_from_role_not_found(client, sysadmin_token):
    response = await client.delete(
        '/security/roles/2/permissions/999999',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Perfil não possui esta permissão'


async def test_remove_permission_from_role_forbidden_for_unit_admin(
    client, session, unit_admin_token
):
    perm = await _new_permission(session)
    session.add(RolePermissions(role_id=2, permission_id=perm.id))
    await session.commit()

    response = await client.delete(
        f'/security/roles/2/permissions/{perm.id}',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
