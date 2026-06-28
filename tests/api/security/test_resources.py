"""Testes de endpoint do CRUD de recursos RBAC (`/security/resources`).

Gating (routers/security/__init__.py): todo `/security` exige
`require_admin` e `/resources` exige `require_system_admin` por cima. Logo,
só admin de sistema escreve; admin de unidade e não-admin tomam 403.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.resources import Permissions, Resources

pytestmark = pytest.mark.anyio


async def _new_resource(session, name='recurso_x', description='desc'):
    resource = Resources(name=name, description=description)
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


# --- Gating --------------------------------------------------------------- #


async def test_list_resources_as_system_admin_ok(client, sysadmin_token):
    response = await client.get(
        '/security/resources/',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['status'] == 'success'


async def test_resources_forbidden_for_unit_admin(client, unit_admin_token):
    response = await client.get(
        '/security/resources/',
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_resources_forbidden_for_nonadmin(client, nonadmin_token):
    response = await client.get(
        '/security/resources/',
        headers={'Authorization': f'Bearer {nonadmin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_resources_requires_token(client):
    response = await client.get('/security/resources/')
    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_resource_forbidden_for_unit_admin(
    client, unit_admin_token
):
    response = await client.post(
        '/security/resources/',
        json={'name': 'x', 'description': 'y'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


# --- CRUD ----------------------------------------------------------------- #


async def test_create_resource_ok(client, session, sysadmin_token):
    response = await client.post(
        '/security/resources/',
        json={'name': 'frota', 'description': 'Gestão de frota'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert data['name'] == 'frota'
    assert data['id']

    db = await session.scalar(
        select(Resources).where(Resources.id == data['id'])
    )
    assert db is not None


async def test_create_resource_validation(client, sysadmin_token):
    response = await client.post(
        '/security/resources/',
        json={'name': '', 'description': 'x'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_resource_ok(client, session, sysadmin_token):
    resource = await _new_resource(session)
    response = await client.put(
        f'/security/resources/{resource.id}',
        json={'description': 'nova descrição'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['description'] == 'nova descrição'


async def test_update_resource_not_found(client, sysadmin_token):
    response = await client.put(
        '/security/resources/999999',
        json={'name': 'x'},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Recurso não encontrado'


async def test_delete_resource_ok(client, session, sysadmin_token):
    resource = await _new_resource(session)
    response = await client.delete(
        f'/security/resources/{resource.id}',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    db = await session.scalar(
        select(Resources).where(Resources.id == resource.id)
    )
    assert db is None


async def test_delete_resource_not_found(client, sysadmin_token):
    response = await client.delete(
        '/security/resources/999999',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_delete_resource_with_linked_permission_conflict(
    client, session, sysadmin_token
):
    resource = await _new_resource(session)
    session.add(
        Permissions(resource_id=resource.id, name='view', description='ver')
    )
    await session.commit()

    response = await client.delete(
        f'/security/resources/{resource.id}',
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.CONFLICT
    msg = response.json()['message']
    assert msg == 'Recurso possui permissões vinculadas'
