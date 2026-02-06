"""
Testes para o endpoint PUT /cegep/soldos/{soldo_id}.

Este endpoint atualiza um soldo existente.
Requer autenticacao.
"""

from datetime import timedelta
from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_update_soldo_success(client, session, token, soldos):
    """Testa atualizacao de soldo com sucesso."""
    soldo = soldos[0]

    update_data = {
        'valor': 5500.00,
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['valor'] == 5500.00

    # Verifica no banco
    await session.refresh(soldo)
    assert soldo.valor == 5500.00


async def test_update_soldo_partial(client, session, token, soldos):
    """Testa atualizacao parcial de soldo."""
    soldo = soldos[0]
    original_pg = soldo.pg

    update_data = {
        'valor': 4800.00,
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que apenas valor foi alterado
    await session.refresh(soldo)
    assert soldo.pg == original_pg
    assert soldo.valor == 4800.00


async def test_update_soldo_change_posto(client, session, token, soldos):
    """Testa atualizacao do posto/graduacao."""
    soldo = soldos[0]

    update_data = {
        'pg': '3s',  # Muda de cb para 3s
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['pg'] == '3s'


async def test_update_soldo_invalid_posto(client, token, soldos):
    """Testa que posto/graduacao invalido falha."""
    soldo = soldos[0]

    update_data = {
        'pg': 'XX',  # Posto invalido
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Posto/Graduacao invalido' in response.json()['message']


async def test_update_soldo_data_fim_before_data_inicio(client, token, soldos):
    """Testa que data_fim <= data_inicio falha na atualizacao."""
    soldo = soldos[0]

    update_data = {
        'data_fim': (soldo.data_inicio - timedelta(days=1)).isoformat(),
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_update_soldo_data_inicio_after_existing_data_fim(
    client, token, soldos
):
    """Testa que data_inicio > data_fim existente falha."""
    # Soldo com data_fim definida (soldos[1])
    soldo = soldos[1]  # 2s com data_fim

    update_data = {
        'data_inicio': (soldo.data_fim + timedelta(days=1)).isoformat(),
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_update_soldo_not_found(client, token):
    """Testa atualizacao de soldo inexistente."""
    update_data = {
        'valor': 5000.00,
    }

    response = await client.put(
        '/cegep/soldos/999999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Soldo nao encontrado' in response.json()['message']


async def test_update_soldo_without_token(client, soldos):
    """Testa que requisicao sem token falha."""
    soldo = soldos[0]

    update_data = {
        'valor': 5000.00,
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_soldo_empty_body(client, session, token, soldos):
    """Testa atualizacao com body vazio nao altera nada."""
    soldo = soldos[0]
    original_valor = soldo.valor

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que nada foi alterado
    await session.refresh(soldo)
    assert soldo.valor == original_valor
