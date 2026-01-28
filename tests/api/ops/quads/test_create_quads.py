"""
Testes para o endpoint POST /ops/quads/.

Este endpoint cria novos quadrinhos (quads) associados a tripulantes.
Requer autenticação.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.quads import Quad

pytestmark = pytest.mark.anyio


async def test_create_quad_success(client, session, trip, token):
    """Testa criação de quadrinho com sucesso."""
    quad_data = [
        {
            'value': date.today().isoformat(),
            'type_id': 1,
            'description': 'Primeiro quadrinho',
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {'detail': 'Quadrinho inserido com sucesso'}

    # Verifica no banco
    db_quad = await session.scalar(
        select(Quad).where(Quad.trip_id == trip.id)
    )
    assert db_quad is not None
    assert db_quad.description == 'Primeiro quadrinho'
    assert db_quad.type_id == 1


async def test_create_multiple_quads_success(client, session, trip, token):
    """Testa criação de múltiplos quadrinhos de uma vez."""
    quad_data = [
        {
            'value': date.today().isoformat(),
            'type_id': 1,
            'description': 'Quad 1',
            'trip_id': trip.id,
        },
        {
            'value': (date.today() + timedelta(days=1)).isoformat(),
            'type_id': 1,
            'description': 'Quad 2',
            'trip_id': trip.id,
        },
        {
            'value': (date.today() + timedelta(days=2)).isoformat(),
            'type_id': 2,
            'description': 'Quad 3',
            'trip_id': trip.id,
        },
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED

    # Verifica no banco
    result = await session.scalars(
        select(Quad).where(Quad.trip_id == trip.id)
    )
    quads = result.all()
    assert len(quads) == 3


async def test_create_quad_with_null_value_success(
    client, session, trip, token
):
    """Testa criação de quadrinho sem valor (NULL)."""
    quad_data = [
        {
            'value': None,
            'type_id': 1,
            'description': 'Quadrinho sem data',
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED

    db_quad = await session.scalar(
        select(Quad).where(Quad.trip_id == trip.id)
    )
    assert db_quad is not None
    assert db_quad.value is None


async def test_create_quad_with_null_description_success(
    client, session, trip, token
):
    """Testa criação de quadrinho sem descrição (NULL)."""
    quad_data = [
        {
            'value': date.today().isoformat(),
            'type_id': 1,
            'description': None,
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED

    db_quad = await session.scalar(
        select(Quad).where(Quad.trip_id == trip.id)
    )
    assert db_quad is not None
    assert db_quad.description is None


async def test_create_quad_duplicate_fails(client, session, trip, token):
    """Testa que duplicata (mesma value, type_id e trip_id) falha."""
    headers = {'Authorization': f'Bearer {token}'}

    # Cria primeiro quadrinho
    quad_data = [
        {
            'value': date.today().isoformat(),
            'type_id': 1,
            'description': 'Original',
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/', json=quad_data, headers=headers
    )
    assert response.status_code == HTTPStatus.CREATED

    # Tenta criar duplicata
    quad_data_dup = [
        {
            'value': date.today().isoformat(),
            'type_id': 1,
            'description': 'Duplicata',
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/', json=quad_data_dup, headers=headers
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'já registrado' in response.json()['detail']


async def test_create_quad_same_value_different_type_success(
    client, session, trip, token
):
    """Testa que mesma data com tipo diferente não é duplicata."""
    headers = {'Authorization': f'Bearer {token}'}
    today = date.today().isoformat()

    # Cria com type_id=1
    response = await client.post(
        '/ops/quads/',
        json=[
            {
                'value': today,
                'type_id': 1,
                'description': 'Tipo 1',
                'trip_id': trip.id,
            }
        ],
        headers=headers,
    )
    assert response.status_code == HTTPStatus.CREATED

    # Cria com type_id=2 (mesmo valor, tipo diferente)
    response = await client.post(
        '/ops/quads/',
        json=[
            {
                'value': today,
                'type_id': 2,
                'description': 'Tipo 2',
                'trip_id': trip.id,
            }
        ],
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED

    result = await session.scalars(
        select(Quad).where(Quad.trip_id == trip.id)
    )
    quads = result.all()
    assert len(quads) == 2


async def test_create_quad_same_value_different_trip_success(
    client, session, trips, token
):
    """Testa que mesma data com tripulante diferente não é duplicata."""
    headers = {'Authorization': f'Bearer {token}'}
    trip, other_trip = trips
    today = date.today().isoformat()

    # Cria para trip
    response = await client.post(
        '/ops/quads/',
        json=[
            {
                'value': today,
                'type_id': 1,
                'description': 'Trip 1',
                'trip_id': trip.id,
            }
        ],
        headers=headers,
    )
    assert response.status_code == HTTPStatus.CREATED

    # Cria para other_trip (mesmo valor, tripulante diferente)
    response = await client.post(
        '/ops/quads/',
        json=[
            {
                'value': today,
                'type_id': 1,
                'description': 'Trip 2',
                'trip_id': other_trip.id,
            }
        ],
        headers=headers,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_quad_missing_required_field_fails(client, trip, token):
    """Testa que campo obrigatório faltando falha."""
    # Falta type_id
    quad_data = [
        {
            'value': date.today().isoformat(),
            'description': 'Sem type_id',
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_quad_invalid_date_format_fails(client, trip, token):
    """Testa que formato de data inválido falha."""
    quad_data = [
        {
            'value': '2024-13-45',  # Data inválida
            'type_id': 1,
            'description': 'Data invalida',
            'trip_id': trip.id,
        }
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_quad_empty_list_success(client, token):
    """Testa que lista vazia não causa erro."""
    response = await client.post(
        '/ops/quads/',
        json=[],
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_multiple_quads_with_null_values_no_duplicate(
    client, session, trip, token
):
    """Testa que múltiplos quads com value=NULL não são duplicatas."""
    quad_data = [
        {
            'value': None,
            'type_id': 1,
            'description': 'Null 1',
            'trip_id': trip.id,
        },
        {
            'value': None,
            'type_id': 1,
            'description': 'Null 2',
            'trip_id': trip.id,
        },
    ]

    response = await client.post(
        '/ops/quads/',
        json=quad_data,
        headers={'Authorization': f'Bearer {token}'},
    )

    # Com value=None, a verificação de duplicidade é pulada
    assert response.status_code == HTTPStatus.CREATED

    result = await session.scalars(
        select(Quad).where(Quad.trip_id == trip.id)
    )
    quads = result.all()
    assert len(quads) == 2


async def test_create_quad_without_token_fails(client, trip):
    """Testa que requisição sem token falha."""
    quad_data = [
        {
            'value': date.today().isoformat(),
            'type_id': 1,
            'description': 'Sem auth',
            'trip_id': trip.id,
        }
    ]

    response = await client.post('/ops/quads/', json=quad_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
