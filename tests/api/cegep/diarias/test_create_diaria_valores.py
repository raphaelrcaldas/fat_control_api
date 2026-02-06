"""
Testes para o endpoint POST /cegep/diarias/valores/.

Este endpoint cria um novo valor de diaria.
Requer autenticacao.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.diarias import DiariaValor

pytestmark = pytest.mark.anyio


async def test_create_diaria_valor_success(client, session, token):
    """Testa criacao de valor de diaria com sucesso."""
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': 320.00,
        'data_inicio': date.today().isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['grupo_pg'] == 1
    assert data['grupo_cid'] == 1
    assert data['valor'] == 320.00
    assert data['status'] == 'vigente'
    assert 'id' in data

    # Verifica no banco
    db_valor = await session.scalar(
        select(DiariaValor).where(DiariaValor.id == data['id'])
    )
    assert db_valor is not None
    assert db_valor.valor == 320.00


async def test_create_diaria_valor_with_data_fim(client, session, token):
    """Testa criacao de valor de diaria com data_fim."""
    today = date.today()
    valor_data = {
        'grupo_pg': 2,
        'grupo_cid': 1,
        'valor': 280.00,
        'data_inicio': today.isoformat(),
        'data_fim': (today + timedelta(days=365)).isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['data_fim'] == (today + timedelta(days=365)).isoformat()


async def test_create_diaria_valor_future_start_date(client, token):
    """Testa criacao de valor com data_inicio futura (status proximo)."""
    future_date = date.today() + timedelta(days=30)
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': 400.00,
        'data_inicio': future_date.isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['status'] == 'proximo'


async def test_create_diaria_valor_data_fim_before_data_inicio(client, token):
    """Testa que data_fim <= data_inicio falha."""
    today = date.today()
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': 300.00,
        'data_inicio': today.isoformat(),
        'data_fim': (today - timedelta(days=1)).isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_create_diaria_valor_data_fim_equal_data_inicio(client, token):
    """Testa que data_fim == data_inicio falha."""
    today = date.today()
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': 300.00,
        'data_inicio': today.isoformat(),
        'data_fim': today.isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_create_diaria_valor_without_token(client):
    """Testa que requisicao sem token falha."""
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': 300.00,
        'data_inicio': date.today().isoformat(),
    }

    response = await client.post('/cegep/diarias/valores/', json=valor_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_diaria_valor_missing_required_field(client, token):
    """Testa que campo obrigatorio faltando falha."""
    # Falta o campo 'valor'
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'data_inicio': date.today().isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_diaria_valor_zero_fails(client, token):
    """Testa que valor zero falha (schema exige valor > 0)."""
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': 0,
        'data_inicio': date.today().isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_diaria_valor_negative_fails(client, token):
    """Testa que valor negativo falha."""
    valor_data = {
        'grupo_pg': 1,
        'grupo_cid': 1,
        'valor': -50.00,
        'data_inicio': date.today().isoformat(),
    }

    response = await client.post(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
        json=valor_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
