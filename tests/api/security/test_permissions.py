"""Testes de endpoint do CRUD de permissões RBAC (`/security/permissions`).

Mesmo gating de resources: admin de sistema escreve; admin de unidade e
não-admin tomam 403 (require_system_admin sobre require_admin).
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
)

pytestmark = pytest.mark.anyio


async def _new_resource(session, name='rec_perm'):
    resource = Resources(name=name, description='desc')
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


async def _new_permission(session, resource_id, name='view'):
    perm = Permissions(resource_id=resource_id, name=name, description='desc')
    session.add(perm)
    await session.commit()
    await session.refresh(perm)
    return perm


# --- Gating --------------------------------------------------------------- #


async def test_list_permissions_as_system_admin_ok(client, sysadmin_token):
    response = await client.get(
        '/security/permissions/',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK


async def test_permissions_forbidden_for_unit_admin(client, unit_admin_token):
    response = await client.get(
        '/security/permissions/',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_permissions_forbidden_for_nonadmin(client, nonadmin_token):
    response = await client.post(
        '/security/permissions/',
        json={'resource_id': 1, 'name': 'view', 'description': 'x'},
        headers={'Authorization': f'Bearer {nonadmin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_permissions_requires_token(client):
    response = await client.get('/security/permissions/')
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# --- CRUD ----------------------------------------------------------------- #


async def test_create_permission_ok(client, session, sysadmin_token):
    resource = await _new_resource(session)
    response = await client.post(
        '/security/permissions/',
        json={
            'resource_id': resource.id,
            'name': 'update',
            'description': 'Editar',
        },
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert data['action'] == 'update'
    assert data['resource'] == resource.name


async def test_create_permission_resource_not_found(client, sysadmin_token):
    response = await client.post(
        '/security/permissions/',
        json={'resource_id': 999999, 'name': 'view', 'description': 'x'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Recurso não encontrado'


async def test_list_permissions_filter_by_resource_name(
    client, session, sysadmin_token
):
    res_a = await _new_resource(session, name='alpha')
    res_b = await _new_resource(session, name='beta')
    await _new_permission(session, res_a.id, name='view')
    await _new_permission(session, res_b.id, name='view')

    response = await client.get(
        '/security/permissions/',
        params={'resource_name': 'alpha'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    items = response.json()['data']
    assert items
    assert all(p['resource'] == 'alpha' for p in items)


async def test_update_permission_ok(client, session, sysadmin_token):
    resource = await _new_resource(session)
    perm = await _new_permission(session, resource.id)
    response = await client.put(
        f'/security/permissions/{perm.id}',
        json={'description': 'descrição nova'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['description'] == 'descrição nova'


async def test_update_permission_not_found(client, sysadmin_token):
    response = await client.put(
        '/security/permissions/999999',
        json={'name': 'x'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Permissão não encontrada'


async def test_delete_permission_ok(client, session, sysadmin_token):
    resource = await _new_resource(session)
    perm = await _new_permission(session, resource.id)
    response = await client.delete(
        f'/security/permissions/{perm.id}',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    db = await session.scalar(
        select(Permissions).where(Permissions.id == perm.id)
    )
    assert db is None


async def test_delete_permission_not_found(client, sysadmin_token):
    response = await client.delete(
        '/security/permissions/999999',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_delete_permission_with_linked_role_conflict(
    client, session, sysadmin_token
):
    resource = await _new_resource(session)
    perm = await _new_permission(session, resource.id)
    # Vincula a permissão à role 'user' (id 2) dos seeds.
    session.add(RolePermissions(role_id=2, permission_id=perm.id))
    await session.commit()

    response = await client.delete(
        f'/security/permissions/{perm.id}',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()['message'] == 'Permissão possui roles vinculados'
