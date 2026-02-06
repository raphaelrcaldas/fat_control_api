"""
Testes para o endpoint PUT /ops/quads/{id}.

Este endpoint atualiza um quadrinho existente. Requer autenticação.
"""

from datetime import date
from http import HTTPStatus

import pytest

from tests.factories import QuadFactory

pytestmark = pytest.mark.anyio


async def test_update_quad_success(client, session, trip, token):
    """Testa atualização de quadrinho com sucesso."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 1, 1),
        description='Original',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': '2024-06-15',
        'description': 'Atualizado',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == 'Quadrinho atualizado'

    # Verifica no banco
    await session.refresh(quad)
    assert quad.value == date(2024, 6, 15)
    assert quad.description == 'Atualizado'


async def test_update_quad_value_only(client, session, trip, token):
    """Testa atualização apenas do valor."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 1, 1),
        description='Manter',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': '2024-12-25',
        'description': 'Manter',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(quad)
    assert quad.value == date(2024, 12, 25)
    assert quad.description == 'Manter'


async def test_update_quad_description_only(client, session, trip, token):
    """Testa atualização apenas da descrição."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 5, 10),
        description='Original',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': '2024-05-10',
        'description': 'Nova descricao',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(quad)
    assert quad.description == 'Nova descricao'


async def test_update_quad_to_null_value(client, session, trip, token):
    """Testa atualização do valor para NULL."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 3, 20),
        description='Com valor',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': None,
        'description': 'Sem valor',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(quad)
    assert quad.value is None


async def test_update_quad_not_found(client, trip, token):
    """Testa atualização de quadrinho inexistente."""
    update_data = {
        'id': 999999,
        'trip_id': trip.id,
        'value': '2024-01-01',
        'description': 'Nao existe',
    }

    response = await client.put(
        '/ops/quads/999999',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Quad not found'


async def test_update_quad_duplicate_fails(client, session, trip, token):
    """Testa que atualizar para duplicata falha."""
    # Cria dois quadrinhos
    quad1 = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 1, 1),
        description='Primeiro',
    )
    quad2 = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 2, 2),
        description='Segundo',
    )

    session.add_all([quad1, quad2])
    await session.commit()
    await session.refresh(quad1)
    await session.refresh(quad2)

    # Tenta atualizar quad2 para ter o mesmo value de quad1
    update_data = {
        'id': quad2.id,
        'trip_id': trip.id,
        'value': '2024-01-01',  # Mesmo que quad1
        'description': 'Duplicata',
    }

    response = await client.put(
        f'/ops/quads/{quad2.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'já registrado' in resp['message']


async def test_update_quad_same_value_allowed(client, session, trip, token):
    """Testa que manter o mesmo valor não é considerado duplicata."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 5, 5),
        description='Original',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    # Atualiza apenas a descrição, mantendo o mesmo value
    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': '2024-05-05',
        'description': 'Nova descricao',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_quad_different_type_not_duplicate(
    client, session, trip, token
):
    """Testa que mesmo valor com tipo diferente não é duplicata."""
    quad_type1 = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 3, 3),
        description='Tipo 1',
    )
    quad_type2 = QuadFactory(
        trip_id=trip.id,
        type_id=2,
        value=date(2024, 4, 4),
        description='Tipo 2',
    )

    session.add_all([quad_type1, quad_type2])
    await session.commit()
    await session.refresh(quad_type2)

    # Atualiza quad_type2 para ter o mesmo value de quad_type1
    # Deve funcionar pois são tipos diferentes
    update_data = {
        'id': quad_type2.id,
        'trip_id': trip.id,
        'value': '2024-03-03',  # Mesmo que quad_type1
        'description': 'Mesmo valor, tipo diferente',
    }

    response = await client.put(
        f'/ops/quads/{quad_type2.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    # O tipo é mantido (não pode ser alterado), então verifica duplicidade
    # dentro do mesmo tipo
    assert response.status_code == HTTPStatus.OK


async def test_update_quad_change_trip_id(client, session, trips, token):
    """Testa mudança de tripulante associado."""
    trip, other_trip = trips

    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date(2024, 7, 7),
        description='Mudanca trip',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    # Muda o trip_id
    update_data = {
        'id': quad.id,
        'trip_id': other_trip.id,  # Novo tripulante
        'value': '2024-07-07',
        'description': 'Mudanca trip',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(quad)
    assert quad.trip_id == other_trip.id


async def test_update_quad_invalid_date_format_fails(
    client, session, trip, token
):
    """Testa que formato de data inválido falha."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date.today(),
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': '2024-13-45',  # Data inválida
        'description': 'Data invalida',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_quad_missing_required_field_fails(
    client, session, trip, token
):
    """Testa que campo obrigatório faltando falha."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date.today(),
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    # Falta trip_id
    update_data = {
        'id': quad.id,
        'value': '2024-01-01',
        'description': 'Falta trip_id',
    }

    response = await client.put(
        f'/ops/quads/{quad.id}',
        json=update_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_quad_without_token_fails(client, session, trip):
    """Testa que requisição sem token falha."""
    quad = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    update_data = {
        'id': quad.id,
        'trip_id': trip.id,
        'value': '2024-01-01',
        'description': 'Sem auth',
    }

    response = await client.put(f'/ops/quads/{quad.id}', json=update_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
