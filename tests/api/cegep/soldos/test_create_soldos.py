"""
Testes para o endpoint POST /cegep/soldos/.

Este endpoint cria um novo registro de soldo.
Requer autenticacao.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.posto_grad import Soldo

pytestmark = pytest.mark.anyio


async def test_create_soldo_success(client, session, token):
    """Testa criacao de soldo com sucesso."""
    soldo_data = {
        'pg': 'cb',
        'data_inicio': date.today().isoformat(),
        'valor': 4500.00,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['pg'] == 'cb'
    assert data['valor'] == 4500.00
    assert 'id' in data

    # Verifica no banco
    db_soldo = await session.scalar(
        select(Soldo).where(Soldo.id == data['id'])
    )
    assert db_soldo is not None
    assert db_soldo.valor == 4500.00


async def test_create_soldo_with_data_fim(client, session, token):
    """Testa criacao de soldo com data_fim."""
    today = date.today()
    soldo_data = {
        'pg': '2s',
        'data_inicio': today.isoformat(),
        'data_fim': (today + timedelta(days=365)).isoformat(),
        'valor': 6000.00,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['data_fim'] == (today + timedelta(days=365)).isoformat()


async def test_create_soldo_invalid_posto(client, token):
    """Testa que posto/graduacao invalido falha."""
    soldo_data = {
        'pg': 'XX',  # Posto invalido
        'data_inicio': date.today().isoformat(),
        'valor': 5000.00,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Posto/Graduacao invalido' in response.json()['message']


async def test_create_soldo_data_fim_before_data_inicio(client, token):
    """Testa que data_fim <= data_inicio falha."""
    today = date.today()
    soldo_data = {
        'pg': 'cb',
        'data_inicio': today.isoformat(),
        'data_fim': (today - timedelta(days=1)).isoformat(),
        'valor': 5000.00,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_create_soldo_data_fim_equal_data_inicio(client, token):
    """Testa que data_fim == data_inicio falha."""
    today = date.today()
    soldo_data = {
        'pg': 'cb',
        'data_inicio': today.isoformat(),
        'data_fim': today.isoformat(),
        'valor': 5000.00,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_create_soldo_without_token(client):
    """Testa que requisicao sem token falha."""
    soldo_data = {
        'pg': 'cb',
        'data_inicio': date.today().isoformat(),
        'valor': 5000.00,
    }

    response = await client.post('/cegep/soldos/', json=soldo_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_soldo_missing_required_field(client, token):
    """Testa que campo obrigatorio faltando falha."""
    # Falta o campo 'valor'
    soldo_data = {
        'pg': 'cb',
        'data_inicio': date.today().isoformat(),
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_soldo_valor_zero_fails(client, token):
    """Testa que valor zero falha (schema exige valor > 0)."""
    soldo_data = {
        'pg': 'cb',
        'data_inicio': date.today().isoformat(),
        'valor': 0,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_soldo_valor_negative_fails(client, token):
    """Testa que valor negativo falha."""
    soldo_data = {
        'pg': 'cb',
        'data_inicio': date.today().isoformat(),
        'valor': -100.00,
    }

    response = await client.post(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
        json=soldo_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
