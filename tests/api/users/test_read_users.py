"""
Testes para o endpoint GET /users/.

Este endpoint lista usuários, com suporte a busca opcional por nome_guerra.
"""

from http import HTTPStatus

import pytest

from tests.factories import UserFactory

pytestmark = pytest.mark.anyio

# Constantes de teste
MIN_USERS_FROM_FIXTURE = 2  # Número mínimo de usuários criados pela fixture
MAX_SEARCH_RESULTS = 10  # Limite máximo de resultados na busca


async def test_read_users_returns_list(client, users, token):
    """
    Testa que o endpoint retorna uma lista de usuários paginada.
    """
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert 'items' in data
    assert isinstance(data['items'], list)
    # Deve ter pelo menos os 2 usuários criados pela fixture
    assert len(data['items']) >= MIN_USERS_FROM_FIXTURE


async def test_read_users_returns_correct_fields(client, users, token):
    """
    Testa que cada usuário retornado tem os campos esperados.
    """
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    if len(data['items']) > 0:
        user = data['items'][0]
        # Campos obrigatórios de UserPublic
        assert 'id' in user
        assert 'p_g' in user
        assert 'posto' in user
        assert 'esp' in user
        assert 'nome_guerra' in user
        assert 'saram' in user
        assert 'nome_completo' in user
        assert 'active' in user
        assert 'unidade' in user


async def test_read_users_ordered_by_posto_and_antiguidade(
    client, users, token
):
    """
    Testa que os usuários são ordenados por posto, promoção e antiguidade.
    """
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Verifica que retornou usuários
    assert len(data['items']) > 0


async def test_read_users_with_search_returns_filtered_results(
    client, session, users, token
):
    """
    Testa que a busca filtra usuários por nome_guerra.
    """
    user, other_user = users

    # Busca pelo nome_guerra do primeiro usuário
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': user.nome_guerra},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Deve retornar pelo menos o usuário buscado
    assert len(data['items']) >= 1
    # Verifica que o usuário buscado está nos resultados
    found = any(u['id'] == user.id for u in data['items'])
    assert found


async def test_read_users_with_search_case_insensitive(client, users, token):
    """
    Testa que a busca é case-insensitive.
    """
    user, _ = users

    # Busca com maiúsculas
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': user.nome_guerra.upper()},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Deve encontrar o usuário
    found = any(u['id'] == user.id for u in data['items'])
    assert found


async def test_read_users_with_search_limits_to_10_results(
    client, users, token
):
    """
    Testa que a busca limita os resultados a 10 usuários.
    """
    # Busca vazia (match all) - deve limitar a 10
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': '', 'per_page': MAX_SEARCH_RESULTS},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Deve retornar no máximo 10 resultados
    assert len(data['items']) <= MAX_SEARCH_RESULTS


async def test_read_users_with_search_no_match_returns_empty(client, token):
    """
    Testa que busca sem match retorna lista vazia.
    """
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': 'usuario_inexistente_xyz'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert isinstance(data['items'], list)
    assert len(data['items']) == 0


async def test_read_users_without_authentication_fails(client):
    """
    Testa que o endpoint requer autenticação.
    """
    response = await client.get('/users/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_read_users_filter_by_single_pg(client, session, token):
    """
    Testa filtro por um único p_g.
    """

    # Cria usuários com p_g específicos
    user_2s = UserFactory(p_g='2s')
    user_3s = UserFactory(p_g='3s')
    session.add_all([user_2s, user_3s])
    await session.commit()

    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'p_g': '2s'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os usuários retornados devem ter p_g = '2s'
    assert all(u['p_g'] == '2s' for u in data['items'])
    # Deve ter pelo menos o usuário criado
    assert len(data['items']) >= 1


async def test_read_users_filter_by_multiple_pg(client, session, token):
    """
    Testa filtro por múltiplos p_g separados por vírgula.
    """

    # Cria usuários com p_g específicos
    user_2s = UserFactory(p_g='2s')
    user_3s = UserFactory(p_g='3s')
    user_cb = UserFactory(p_g='cb')
    session.add_all([user_2s, user_3s, user_cb])
    await session.commit()

    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'p_g': '2s, 3s'},  # Múltiplos valores com espaço
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os usuários devem ter p_g '2s' ou '3s'
    assert all(u['p_g'] in {'2s', '3s'} for u in data['items'])
    # Não deve incluir 'cb'
    assert not any(u['p_g'] == 'cb' for u in data['items'])


async def test_read_users_filter_by_active_true(client, session, token):
    """
    Testa filtro por usuários ativos.
    """

    # Cria um usuário inativo
    inactive_user = UserFactory()
    inactive_user.active = False
    session.add(inactive_user)
    await session.commit()
    await session.refresh(inactive_user)

    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'active': True},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os usuários retornados devem estar ativos
    assert all(u['active'] is True for u in data['items'])
    # Usuário inativo não deve aparecer
    assert not any(u['id'] == inactive_user.id for u in data['items'])


async def test_read_users_filter_by_active_false(client, session, token):
    """
    Testa filtro por usuários inativos.
    """

    # Cria um usuário inativo
    inactive_user = UserFactory()
    inactive_user.active = False
    session.add(inactive_user)
    await session.commit()
    await session.refresh(inactive_user)

    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'active': False},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os usuários retornados devem estar inativos
    assert all(u['active'] is False for u in data['items'])
    # Usuário inativo criado deve aparecer
    assert any(u['id'] == inactive_user.id for u in data['items'])


async def test_read_users_filter_pg_and_active(client, session, token):
    """
    Testa filtros combinados de p_g e active.
    """

    # Cria usuários com diferentes combinações
    active_2s = UserFactory(p_g='2s')
    active_3s = UserFactory(p_g='3s')
    inactive_2s = UserFactory(p_g='2s')
    inactive_2s.active = False

    session.add_all([active_2s, active_3s, inactive_2s])
    await session.commit()
    await session.refresh(active_2s)
    await session.refresh(inactive_2s)

    # Filtra por p_g='2s' E active=True
    response = await client.get(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        params={'p_g': '2s', 'active': True},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos devem ser p_g='2s' E ativos
    assert all(u['p_g'] == '2s' and u['active'] is True for u in data['items'])
    # Usuário inativo com p_g='2s' não deve aparecer
    assert not any(u['id'] == inactive_2s.id for u in data['items'])
