"""
Testes para os endpoints GET /cegep/soldos/.

Endpoints testados:
- GET /cegep/soldos/ - Listar com filtros
- GET /cegep/soldos/{soldo_id} - Buscar por ID
- GET /cegep/soldos/stats - Estatisticas
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


# ============================================================
# GET /cegep/soldos/ - Listar todos
# ============================================================


async def test_list_soldos_success(client, token, soldos):
    """Testa listagem de soldos com sucesso."""
    response = await client.get(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3


async def test_list_soldos_filter_by_circulo(client, token, soldos):
    """Testa filtro por circulo."""
    # 'cb' pertence ao circulo 'praca'
    response = await client.get(
        '/cegep/soldos/?circulo=praça',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os soldos retornados devem ser do circulo praca
    for soldo in data:
        assert soldo['posto_grad']['circulo'] == 'praça'


async def test_list_soldos_filter_active_only(client, token, soldos):
    """Testa filtro active_only (apenas soldos vigentes)."""
    response = await client.get(
        '/cegep/soldos/?active_only=true',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Deve excluir o soldo expirado (1t)
    pgs = [s['pg'] for s in data]
    assert '1t' not in pgs  # 1t esta expirado na fixture


async def test_list_soldos_filter_combined(client, token, soldos):
    """Testa filtros combinados (circulo + active_only)."""
    response = await client.get(
        '/cegep/soldos/?circulo=grad&active_only=true',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # 2s e grad e vigente
    for soldo in data:
        assert soldo['posto_grad']['circulo'] == 'grad'


async def test_list_soldos_ordered_by_data_inicio_desc(client, token, soldos):
    """Testa que os soldos sao ordenados por data_inicio decrescente."""
    response = await client.get(
        '/cegep/soldos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Verifica ordenacao decrescente por data_inicio
    datas = [s['data_inicio'] for s in data]
    assert datas == sorted(datas, reverse=True)


async def test_list_soldos_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/soldos/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/soldos/{soldo_id} - Buscar por ID
# ============================================================


async def test_get_soldo_by_id_success(client, token, soldos):
    """Testa busca por ID com sucesso."""
    soldo = soldos[0]

    response = await client.get(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['id'] == soldo.id
    assert data['pg'] == soldo.pg
    assert data['valor'] == soldo.valor


async def test_get_soldo_by_id_not_found(client, token):
    """Testa busca por ID inexistente."""
    response = await client.get(
        '/cegep/soldos/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Soldo nao encontrado' in response.json()['detail']


async def test_get_soldo_by_id_without_token(client, soldos):
    """Testa que requisicao sem token falha."""
    soldo = soldos[0]

    response = await client.get(f'/cegep/soldos/{soldo.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/soldos/stats - Estatisticas
# ============================================================


async def test_get_soldo_stats_success(client, token, soldos):
    """Testa estatisticas de soldos com sucesso."""
    response = await client.get(
        '/cegep/soldos/stats',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert 'total' in data
    assert 'min_valor' in data
    assert 'max_valor' in data
    assert data['total'] >= 3


async def test_get_soldo_stats_filter_by_circulo(client, token, soldos):
    """Testa estatisticas filtradas por circulo."""
    response = await client.get(
        '/cegep/soldos/stats?circulo=grad',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    # Apenas 2s (grad) deve ser contado
    assert data['total'] >= 1


async def test_get_soldo_stats_empty(client, token):
    """Testa estatisticas quando nao ha soldos."""
    # Filtra por circulo que nao existe
    response = await client.get(
        '/cegep/soldos/stats?circulo=inexistente',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['total'] == 0
    assert data['min_valor'] is None
    assert data['max_valor'] is None


async def test_get_soldo_stats_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/soldos/stats')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
