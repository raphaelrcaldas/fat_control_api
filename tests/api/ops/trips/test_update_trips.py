"""
Testes para o endpoint PUT /ops/trips/{id}.

Este endpoint atualiza um tripulante existente.
"""

from http import HTTPStatus

import pytest

from tests.factories import TripFactory

pytestmark = pytest.mark.anyio


async def test_update_trip_success(client, trip, org_admin_token):
    """Testa atualização de tripulante com sucesso."""
    update_data = {
        'trig': 'new',
        'active': True,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert 'message' in resp
    assert 'data' in resp
    assert resp['data']['trig'] == 'new'


async def test_update_trip_returns_correct_message(
    client, trip, org_admin_token
):
    """Testa que a mensagem de sucesso está correta."""
    update_data = {
        'trig': 'upd',
        'active': True,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert resp['message'] == 'Tripulante atualizado com sucesso'


async def test_update_trip_change_trig(client, trip, org_admin_token):
    """Testa alteração do trigrama."""
    original_trig = trip.trig

    update_data = {
        'trig': 'xyz',
        'active': trip.active,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert resp['data']['trig'] == 'xyz'
    assert resp['data']['trig'] != original_trig


async def test_update_trip_change_active(client, trip, org_admin_token):
    """Testa alteração do status ativo."""
    update_data = {
        'trig': trip.trig,
        'active': False,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert resp['data']['active'] is False


async def test_update_trip_not_found(client, org_admin_token):
    """Testa que retorna 404 para tripulante inexistente."""
    update_data = {
        'trig': 'abc',
        'active': True,
    }

    response = await client.put(
        '/ops/trips/99999',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Tripulante não encontrado'


async def test_update_trip_duplicate_trig_same_uae_fails(
    client, session, trips, org_admin_token
):
    """Testa que não permite trigrama duplicado na mesma UAE."""
    trip, other_trip = trips

    # Tenta atualizar trip para ter o mesmo trig de other_trip
    update_data = {
        'trig': other_trip.trig,
        'active': True,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Trigrama já registrado'


async def test_update_trip_same_trig_allowed(client, trip, org_admin_token):
    """Testa que pode manter o mesmo trigrama (não é duplicata de si mesmo)."""
    update_data = {
        'trig': trip.trig,  # Mesmo trigrama
        'active': False,  # Muda apenas o active
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert resp['data']['trig'] == trip.trig
    assert resp['data']['active'] is False


async def test_update_trip_trig_too_short_fails(client, trip, org_admin_token):
    """Testa que trigrama com menos de 3 caracteres falha."""
    update_data = {
        'trig': 'ab',  # Menos de 3 caracteres
        'active': True,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_trip_trig_too_long_fails(client, trip, org_admin_token):
    """Testa que trigrama com mais de 3 caracteres falha."""
    update_data = {
        'trig': 'abcd',  # Mais de 3 caracteres
        'active': True,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_trip_missing_trig_fails(client, trip, org_admin_token):
    """Testa que trig é obrigatório."""
    update_data = {
        'active': True,
    }

    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_trip_without_authentication_fails(client, trip):
    """Testa que o endpoint requer autenticação."""
    update_data = {
        'trig': 'abc',
        'active': True,
    }

    response = await client.put(f'/ops/trips/{trip.id}', json=update_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_trip_without_permission_forbidden(
    client, trip, org_token
):
    """Sem grant trips.update na org ativa → 403."""
    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {org_token}'},
        json={'trig': 'abc', 'active': True},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_update_trip_missing_active_org_fails(client, trip, token):
    """Sem org ativa no token → 400."""
    response = await client.put(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'trig': 'abc', 'active': True},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_trip_cross_org_404(
    client, session, users, org_admin_token
):
    """Tripulante de outra org não é atualizável (escopo por uae) → 404."""
    _, other = users
    foreign = TripFactory(user_id=other.id, uae='1gt')
    session.add(foreign)
    await session.commit()
    await session.refresh(foreign)

    response = await client.put(
        f'/ops/trips/{foreign.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json={'trig': 'zzz', 'active': True},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
