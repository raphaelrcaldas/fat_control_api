"""
Testes para o endpoint GET /ops/quads/trip/{trip_id}.

Este endpoint lista os quadrinhos de um tripulante específico,
filtrados por tipo (type_id). Requer autenticação.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import QuadFactory

pytestmark = pytest.mark.anyio


async def test_read_quads_by_trip_success(client, session, trip, token):
    """Testa listagem de quadrinhos por tripulante com sucesso."""
    # Cria quadrinhos de teste
    quad1 = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date.today(),
        description='Quad 1',
    )
    quad2 = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date.today() + timedelta(days=1),
        description='Quad 2',
    )

    session.add_all([quad1, quad2])
    await session.commit()

    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 2


async def test_read_quads_by_trip_filters_by_type(
    client, session, trip, token
):
    """Testa que apenas quads do tipo especificado são retornados."""
    quad_type1 = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    quad_type2 = QuadFactory(trip_id=trip.id, type_id=2, value=date.today())

    session.add_all([quad_type1, quad_type2])
    await session.commit()

    # Busca apenas type_id=1
    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['type_id'] == 1


async def test_read_quads_by_trip_empty_result(client, session, trip, token):
    """Testa que retorna lista vazia quando não há quadrinhos."""
    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_read_quads_by_trip_ordered_by_value_desc(
    client, session, trip, token
):
    """Testa que quads são ordenados por value DESC (NULLs por último)."""
    quad1 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 1))
    quad2 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 6, 15))
    quad3 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 3, 10))

    session.add_all([quad1, quad2, quad3])
    await session.commit()

    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Deve estar em ordem DESC: 2024-06-15, 2024-03-10, 2024-01-01
    assert data[0]['value'] == '2024-06-15'
    assert data[1]['value'] == '2024-03-10'
    assert data[2]['value'] == '2024-01-01'


async def test_read_quads_by_trip_nulls_last(client, session, trip, token):
    """Testa que quads com value=NULL aparecem por último."""
    quad_with_value = QuadFactory(
        trip_id=trip.id, type_id=1, value=date(2024, 5, 1)
    )
    quad_null = QuadFactory(trip_id=trip.id, type_id=1, value=None)

    session.add_all([quad_with_value, quad_null])
    await session.commit()

    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 2
    # O primeiro tem valor, o último é NULL
    assert data[0]['value'] == '2024-05-01'
    assert data[1]['value'] is None


async def test_read_quads_by_trip_only_returns_own_quads(
    client, session, trips, token
):
    """Testa que apenas quads do tripulante solicitado são retornados."""
    trip, other_trip = trips

    quad_trip = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    quad_other = QuadFactory(
        trip_id=other_trip.id, type_id=1, value=date.today()
    )

    session.add_all([quad_trip, quad_other])
    await session.commit()

    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1


async def test_read_quads_by_trip_missing_type_id_fails(client, trip, token):
    """Testa que requisição sem type_id falha."""
    response = await client.get(
        f'/ops/quads/trip/{trip.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_read_quads_by_trip_response_format(
    client, session, trip, token
):
    """Testa o formato da resposta (QuadPublic schema)."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 7, 20),
        description='Teste formato',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    response = await client.get(
        f'/ops/quads/trip/{trip.id}?type_id=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1

    quad_response = data[0]
    assert 'id' in quad_response
    assert 'value' in quad_response
    assert 'type_id' in quad_response
    assert 'description' in quad_response
    assert quad_response['value'] == '2024-07-20'
    assert quad_response['type_id'] == 1
    assert quad_response['description'] == 'Teste formato'


async def test_read_quads_by_trip_without_token_fails(client, trip):
    """Testa que requisição sem token falha."""
    response = await client.get(f'/ops/quads/trip/{trip.id}?type_id=1')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
