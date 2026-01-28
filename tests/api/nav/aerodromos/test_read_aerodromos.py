"""
Testes para os endpoints GET /nav/aerodromos/.

Endpoints testados:
- GET /nav/aerodromos/ - Listar todos
- GET /nav/aerodromos/{id} - Buscar por ID
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


# ============================================================
# GET /nav/aerodromos/ - Listar todos
# ============================================================


async def test_list_aerodromos_success(client, token, aerodromos):
    """Testa listagem de aerodromos com sucesso."""
    response = await client.get(
        '/nav/aerodromos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3

    # Verifica estrutura do retorno
    item = data[0]
    assert 'id' in item
    assert 'nome' in item
    assert 'codigo_icao' in item
    assert 'latitude' in item
    assert 'longitude' in item


async def test_list_aerodromos_includes_cidade(client, token, aerodromos):
    """Testa que a listagem inclui informacoes da cidade."""
    response = await client.get(
        '/nav/aerodromos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Aerodromos com codigo_cidade devem ter cidade populada
    aerodromos_com_cidade = [a for a in data if a['codigo_cidade'] is not None]
    assert len(aerodromos_com_cidade) >= 2

    for aerodromo in aerodromos_com_cidade:
        assert aerodromo['cidade'] is not None
        assert 'nome' in aerodromo['cidade']


async def test_list_aerodromos_includes_base_aerea(client, token, aerodromos):
    """Testa que a listagem inclui informacoes de base aerea."""
    response = await client.get(
        '/nav/aerodromos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Encontra o aerodromo com base aerea (SBBR)
    brasilia = next((a for a in data if a['codigo_icao'] == 'SBBR'), None)
    assert brasilia is not None
    assert brasilia['base_aerea'] is not None
    assert brasilia['base_aerea']['sigla'] == 'BABR'


async def test_list_aerodromos_empty(client, session, token):
    """Testa listagem quando nao ha aerodromos."""
    # Sem a fixture aerodromos, a lista deve estar vazia
    response = await client.get(
        '/nav/aerodromos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data == []


async def test_list_aerodromos_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/nav/aerodromos/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /nav/aerodromos/{id} - Buscar por ID
# ============================================================


async def test_get_aerodromo_by_id_success(client, token, aerodromos):
    """Testa busca por ID com sucesso."""
    aerodromo = aerodromos[0]

    response = await client.get(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['id'] == aerodromo.id
    assert data['nome'] == aerodromo.nome
    assert data['codigo_icao'] == aerodromo.codigo_icao


async def test_get_aerodromo_by_id_includes_cidade(client, token, aerodromos):
    """Testa que busca por ID inclui cidade."""
    # SBSP tem codigo_cidade
    aerodromo = aerodromos[0]

    response = await client.get(
        f'/nav/aerodromos/{aerodromo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['cidade'] is not None
    assert data['cidade']['nome'] == 'São Paulo'


async def test_get_aerodromo_by_id_not_found(client, token):
    """Testa busca por ID inexistente."""
    response = await client.get(
        '/nav/aerodromos/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrado' in response.json()['detail']


async def test_get_aerodromo_by_id_without_token(client, aerodromos):
    """Testa que requisicao sem token falha."""
    aerodromo = aerodromos[0]

    response = await client.get(f'/nav/aerodromos/{aerodromo.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
