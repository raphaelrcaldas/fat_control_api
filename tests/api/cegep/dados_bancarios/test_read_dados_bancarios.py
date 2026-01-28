"""
Testes para os endpoints GET /cegep/dados-bancarios/.

Endpoints testados:
- GET /cegep/dados-bancarios/ - Listar com filtros
- GET /cegep/dados-bancarios/{dados_id} - Buscar por ID
- GET /cegep/dados-bancarios/user/{user_id} - Buscar por usuario
"""

from http import HTTPStatus

import pytest

from tests.factories import DadosBancariosFactory

pytestmark = pytest.mark.anyio


# ============================================================
# GET /cegep/dados-bancarios/ - Listar todos
# ============================================================


async def test_list_dados_bancarios_success(
    client, session, users, token, dados_bancarios
):
    """Testa listagem de dados bancarios com sucesso."""
    response = await client.get(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Verifica que retornou os dados com usuario
    item = data[0]
    assert 'id' in item
    assert 'banco' in item
    assert 'user' in item
    assert 'nome_guerra' in item['user']


async def test_list_dados_bancarios_filter_by_user_id(
    client, session, users, token, dados_bancarios
):
    """Testa filtro por user_id."""
    user, _ = users

    response = await client.get(
        f'/cegep/dados-bancarios/?user_id={user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1
    assert data[0]['user_id'] == user.id


async def test_list_dados_bancarios_filter_by_search(
    client, session, users, token, dados_bancarios
):
    """Testa filtro por search (nome_guerra ou nome_completo)."""
    user, _ = users

    response = await client.get(
        f'/cegep/dados-bancarios/?search={user.nome_guerra}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) >= 1
    assert any(d['user_id'] == user.id for d in data)


async def test_list_dados_bancarios_filter_no_results(
    client, token, dados_bancarios
):
    """Testa filtro que nao retorna resultados."""
    response = await client.get(
        '/cegep/dados-bancarios/?user_id=999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data == []


async def test_list_dados_bancarios_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/dados-bancarios/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/dados-bancarios/{dados_id} - Buscar por ID
# ============================================================


async def test_get_dados_bancarios_by_id_success(
    client, token, dados_bancarios
):
    """Testa busca por ID com sucesso."""
    response = await client.get(
        f'/cegep/dados-bancarios/{dados_bancarios.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['id'] == dados_bancarios.id
    assert data['banco'] == dados_bancarios.banco
    assert 'user' in data


async def test_get_dados_bancarios_by_id_not_found(client, token):
    """Testa busca por ID inexistente."""
    response = await client.get(
        '/cegep/dados-bancarios/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Dados bancários não encontrados' in response.json()['detail']


async def test_get_dados_bancarios_by_id_without_token(
    client, dados_bancarios
):
    """Testa que requisicao sem token falha."""
    response = await client.get(
        f'/cegep/dados-bancarios/{dados_bancarios.id}'
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/dados-bancarios/user/{user_id} - Buscar por usuario
# ============================================================


async def test_get_dados_bancarios_by_user_success(
    client, users, token, dados_bancarios
):
    """Testa busca por user_id com sucesso."""
    user, _ = users

    response = await client.get(
        f'/cegep/dados-bancarios/user/{user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data['user_id'] == user.id
    assert data['banco'] == dados_bancarios.banco


async def test_get_dados_bancarios_by_user_not_found(client, users, token):
    """Testa busca por user_id sem dados bancarios."""
    _, other_user = users

    response = await client.get(
        f'/cegep/dados-bancarios/user/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrados para este usuário' in response.json()['detail']


async def test_get_dados_bancarios_by_user_without_token(client, users):
    """Testa que requisicao sem token falha."""
    user, _ = users

    response = await client.get(f'/cegep/dados-bancarios/user/{user.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_list_multiple_dados_bancarios(client, session, users, token):
    """Testa listagem com multiplos registros."""
    user, other_user = users

    # Cria dados bancarios para ambos usuarios
    dados1 = DadosBancariosFactory(
        user_id=user.id,
        banco='Banco 1',
        codigo_banco='001',
    )
    dados2 = DadosBancariosFactory(
        user_id=other_user.id,
        banco='Banco 2',
        codigo_banco='002',
    )

    session.add_all([dados1, dados2])
    await session.commit()

    response = await client.get(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 2

    bancos = [d['banco'] for d in data]
    assert 'Banco 1' in bancos
    assert 'Banco 2' in bancos
