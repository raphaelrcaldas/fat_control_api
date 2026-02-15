"""
Testes para os endpoints CRUD de Aeronaves (/ops/aeronaves/).
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


# ========================================
# POST /ops/aeronaves/ (Create)
# ========================================


async def test_create_aeronave_success(client, token):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2860',
            'active': True,
            'sit': 'DI',
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['matricula'] == '2860'
    assert data['data']['active'] is True
    assert data['data']['sit'] == 'DI'


async def test_create_aeronave_with_obs_and_prox_insp(
    client, token
):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2861',
            'active': True,
            'sit': 'DO',
            'obs': 'Restrição no radar',
            'prox_insp': '2026-06-15',
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['data']['obs'] == 'Restrição no radar'
    assert data['data']['prox_insp'] == '2026-06-15'


async def test_create_aeronave_duplicate_matricula_fails(
    client, token, aeronave
):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': aeronave.matricula,
            'active': True,
            'sit': 'DI',
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_create_aeronave_invalid_sit_fails(
    client, token
):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2870',
            'active': True,
            'sit': 'X',
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_aeronave_matricula_not_4_digits_fails(
    client, token
):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '123',
            'active': True,
            'sit': 'DI',
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_aeronave_matricula_non_numeric_fails(
    client, token
):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': 'ABCD',
            'active': True,
            'sit': 'DI',
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_aeronave_without_auth_fails(client):
    response = await client.post(
        '/ops/aeronaves/',
        json={
            'matricula': '2880',
            'active': True,
            'sit': 'DI',
        },
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ========================================
# GET /ops/aeronaves/ (List)
# ========================================


async def test_list_aeronaves_success(
    client, token, aeronaves
):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['total'] == 3
    assert len(data['data']) == 3


async def test_list_aeronaves_filter_by_sit(
    client, token, aeronaves
):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        params={'sit': 'DI'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['total'] == 1
    assert data['data'][0]['sit'] == 'DI'


async def test_list_aeronaves_filter_by_active(
    client, token, aeronaves
):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        params={'active': 'true'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['total'] == 2
    assert all(a['active'] for a in data['data'])


async def test_list_aeronaves_empty(client, token):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['total'] == 0
    assert data['data'] == []


# ========================================
# GET /ops/aeronaves/{matricula} (Detail)
# ========================================


async def test_get_aeronave_success(
    client, token, aeronave
):
    response = await client.get(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['matricula'] == aeronave.matricula


async def test_get_aeronave_not_found(client, token):
    response = await client.get(
        '/ops/aeronaves/9999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


# ========================================
# PUT /ops/aeronaves/{matricula} (Update)
# ========================================


async def test_update_aeronave_success(
    client, token, aeronave
):
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token}'},
        json={'sit': 'IS', 'obs': 'Entrou em inspeção'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['sit'] == 'IS'
    assert data['data']['obs'] == 'Entrou em inspeção'


async def test_update_aeronave_partial(
    client, token, aeronave
):
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token}'},
        json={'active': False},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['data']['active'] is False
    assert data['data']['sit'] == 'DI'


async def test_update_aeronave_not_found(client, token):
    response = await client.put(
        '/ops/aeronaves/9999',
        headers={'Authorization': f'Bearer {token}'},
        json={'sit': 'DI'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
