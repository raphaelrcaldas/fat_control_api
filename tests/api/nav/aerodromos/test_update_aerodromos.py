"""
Testes para o endpoint PUT /nav/aerodromos/{id}.

Este endpoint atualiza um aerodromo existente.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_update_aerodromo_success(client, session, token, aerodromos):
    """Testa atualizacao de aerodromo com sucesso."""
    aerodromo = aerodromos[0]

    update_data = {
        'nome': 'Aeroporto de Congonhas - Atualizado',
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['nome'] == 'Aeroporto de Congonhas - Atualizado'

    # Verifica no banco
    await session.refresh(aerodromo)
    assert aerodromo.nome == 'Aeroporto de Congonhas - Atualizado'


async def test_update_aerodromo_partial(client, session, token, aerodromos):
    """Testa atualizacao parcial de aerodromo."""
    aerodromo = aerodromos[0]
    original_nome = aerodromo.nome

    update_data = {
        'elevacao': 850.0,
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que apenas elevacao foi alterada
    await session.refresh(aerodromo)
    assert aerodromo.nome == original_nome
    assert aerodromo.elevacao == 850.0


async def test_update_aerodromo_change_icao(
    client, session, token, aerodromos
):
    """Testa atualizacao do codigo ICAO."""
    aerodromo = aerodromos[2]  # SBGL

    update_data = {
        'codigo_icao': 'SBRF',  # Novo codigo unico
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['codigo_icao'] == 'SBRF'


async def test_update_aerodromo_duplicate_icao_fails(
    client, token, aerodromos
):
    """Testa que codigo ICAO duplicado falha na atualizacao."""
    aerodromo = aerodromos[2]  # SBGL

    update_data = {
        'codigo_icao': 'SBSP',  # Ja existe (aerodromos[0])
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'ICAO já cadastrado' in resp['message']


async def test_update_aerodromo_same_icao_success(
    client, session, token, aerodromos
):
    """Testa que manter o mesmo ICAO funciona."""
    aerodromo = aerodromos[0]

    update_data = {
        'codigo_icao': 'SBSP',  # Mesmo codigo do aerodromo
        'nome': 'Nome Atualizado',
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['codigo_icao'] == 'SBSP'
    assert data['nome'] == 'Nome Atualizado'


async def test_update_aerodromo_add_base_aerea(
    client, session, token, aerodromos
):
    """Testa adicao de base aerea via atualizacao."""
    aerodromo = aerodromos[0]  # SBSP - sem base_aerea

    update_data = {
        'base_aerea': {
            'nome': 'Base Aérea de São Paulo',
            'sigla': 'BASP',
        },
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['base_aerea'] is not None
    assert data['base_aerea']['sigla'] == 'BASP'


async def test_update_aerodromo_not_found(client, token):
    """Testa atualizacao de aerodromo inexistente."""
    update_data = {
        'nome': 'Teste',
    }

    response = await client.put(
        '/nav/aerodromos/999999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'não encontrado' in resp['message']


async def test_update_aerodromo_without_token(client, aerodromos):
    """Testa que requisicao sem token falha."""
    aerodromo = aerodromos[0]

    update_data = {
        'nome': 'Teste',
    }

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_aerodromo_empty_body(client, session, token, aerodromos):
    """Testa atualizacao com body vazio nao altera nada."""
    aerodromo = aerodromos[0]
    original_nome = aerodromo.nome

    response = await client.put(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que nada foi alterado
    await session.refresh(aerodromo)
    assert aerodromo.nome == original_nome
