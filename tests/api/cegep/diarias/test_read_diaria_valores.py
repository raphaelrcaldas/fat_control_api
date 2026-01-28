"""
Testes para os endpoints GET /cegep/diarias/.

Endpoints testados:
- GET /cegep/diarias/valores/ - Listar valores
- GET /cegep/diarias/valores/{valor_id} - Buscar por ID
- GET /cegep/diarias/grupos-cidade/ - Listar grupos cidade
- GET /cegep/diarias/grupos-pg/ - Listar grupos P/G
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


# ============================================================
# GET /cegep/diarias/valores/ - Listar valores
# ============================================================


async def test_list_diaria_valores_success(client, token, diaria_valores):
    """Testa listagem de valores de diarias com sucesso."""
    response = await client.get(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4

    # Verifica estrutura do retorno
    item = data[0]
    assert 'id' in item
    assert 'grupo_pg' in item
    assert 'grupo_cid' in item
    assert 'valor' in item
    assert 'status' in item


async def test_list_diaria_valores_filter_by_grupo_cid(
    client, token, diaria_valores
):
    """Testa filtro por grupo de cidade."""
    response = await client.get(
        '/cegep/diarias/valores/?grupo_cid=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os valores devem ser do grupo_cid filtrado
    for valor in data:
        assert valor['grupo_cid'] == 1


async def test_list_diaria_valores_filter_by_grupo_pg(
    client, token, diaria_valores
):
    """Testa filtro por grupo de P/G."""
    response = await client.get(
        '/cegep/diarias/valores/?grupo_pg=1',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os valores devem ser do grupo_pg filtrado
    for valor in data:
        assert valor['grupo_pg'] == 1


async def test_list_diaria_valores_filter_active_only(
    client, token, diaria_valores
):
    """Testa filtro active_only (apenas valores vigentes)."""
    response = await client.get(
        '/cegep/diarias/valores/?active_only=true',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os valores devem ter status 'vigente'
    for valor in data:
        assert valor['status'] == 'vigente'


async def test_list_diaria_valores_status_calculated(
    client, token, diaria_valores
):
    """Testa que o status e calculado corretamente."""
    response = await client.get(
        '/cegep/diarias/valores/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Verifica que existem diferentes status
    statuses = {v['status'] for v in data}
    # Fixture cria: 2 vigentes, 1 anterior, 1 proximo
    assert 'vigente' in statuses
    assert 'anterior' in statuses
    assert 'proximo' in statuses


async def test_list_diaria_valores_filter_combined(
    client, token, diaria_valores
):
    """Testa filtros combinados (grupo_pg + active_only)."""
    response = await client.get(
        '/cegep/diarias/valores/?grupo_pg=1&active_only=true',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    for valor in data:
        assert valor['grupo_pg'] == 1
        assert valor['status'] == 'vigente'


async def test_list_diaria_valores_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/diarias/valores/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/diarias/valores/{valor_id} - Buscar por ID
# ============================================================


async def test_get_diaria_valor_by_id_success(client, token, diaria_valores):
    """Testa busca por ID com sucesso."""
    valor = diaria_valores[0]

    response = await client.get(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['id'] == valor.id
    assert data['valor'] == valor.valor
    assert 'status' in data


async def test_get_diaria_valor_by_id_not_found(client, token):
    """Testa busca por ID inexistente."""
    response = await client.get(
        '/cegep/diarias/valores/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrado' in response.json()['detail']


async def test_get_diaria_valor_by_id_without_token(client, diaria_valores):
    """Testa que requisicao sem token falha."""
    valor = diaria_valores[0]

    response = await client.get(f'/cegep/diarias/valores/{valor.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/diarias/grupos-cidade/ - Listar grupos cidade
# ============================================================


async def test_list_grupos_cidade_success(client, token):
    """Testa listagem de grupos de cidade com sucesso."""
    response = await client.get(
        '/cegep/diarias/grupos-cidade/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3  # Conftest cria 3 grupos

    # Verifica estrutura
    item = data[0]
    assert 'id' in item
    assert 'grupo' in item
    assert 'cidade_id' in item
    assert 'cidade' in item
    assert item['cidade']['nome'] is not None


async def test_list_grupos_cidade_includes_cidade_info(client, token):
    """Testa que os grupos incluem informacoes da cidade."""
    response = await client.get(
        '/cegep/diarias/grupos-cidade/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    for grupo in data:
        cidade = grupo['cidade']
        assert 'codigo' in cidade
        assert 'nome' in cidade
        assert 'uf' in cidade


async def test_list_grupos_cidade_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/diarias/grupos-cidade/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/diarias/grupos-pg/ - Listar grupos P/G
# ============================================================


async def test_list_grupos_pg_success(client, token):
    """Testa listagem de grupos de P/G com sucesso."""
    response = await client.get(
        '/cegep/diarias/grupos-pg/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 5  # Conftest cria 5 grupos

    # Verifica estrutura
    item = data[0]
    assert 'id' in item
    assert 'grupo' in item
    assert 'pg_short' in item
    assert 'pg_mid' in item
    assert 'circulo' in item


async def test_list_grupos_pg_includes_posto_info(client, token):
    """Testa que os grupos incluem informacoes do posto/graduacao."""
    response = await client.get(
        '/cegep/diarias/grupos-pg/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    for grupo in data:
        # pg_mid e circulo vem do join com PostoGrad
        assert grupo['pg_mid'] is not None
        assert grupo['circulo'] is not None


async def test_list_grupos_pg_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/diarias/grupos-pg/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
