"""
Testes para o endpoint GET /users/{user_id}.

Este endpoint busca um usuário específico por ID.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_get_user_success(client, users, token):
    """
    Testa que é possível buscar um usuário por ID.
    """
    user, _ = users

    response = await client.get(
        f'/users/{user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Verifica que retornou o usuário correto
    assert data['nome_guerra'] == user.nome_guerra
    assert data['saram'] == user.saram

    # Verifica campos obrigatórios de UserFull
    assert 'p_g' in data
    assert 'posto' in data
    assert 'esp' in data
    assert 'nome_guerra' in data
    assert 'nome_completo' in data
    assert 'saram' in data
    assert 'cpf' in data
    assert 'email_fab' in data
    assert 'email_pess' in data
    assert 'unidade' in data


async def test_get_user_returns_full_details(client, users, token):
    """
    Testa que o endpoint retorna todos os detalhes do usuário (UserFull).
    """
    user, _ = users

    response = await client.get(
        f'/users/{user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # UserFull deve incluir todos os campos de UserSchema + posto
    assert 'posto' in data
    assert isinstance(data['posto'], dict)
    assert 'short' in data['posto']


async def test_get_user_not_found(client, token):
    """
    Testa que buscar usuário inexistente retorna 404.
    """
    response = await client.get(
        '/users/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {'detail': 'User not found'}


async def test_get_user_with_different_users(client, users, token):
    """
    Testa que cada ID retorna o usuário correto.
    """
    user1, user2 = users

    response1 = await client.get(
        f'/users/{user1.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    response2 = await client.get(
        f'/users/{user2.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response1.status_code == HTTPStatus.OK
    assert response2.status_code == HTTPStatus.OK

    data1 = response1.json()
    data2 = response2.json()

    # Verifica que são usuários diferentes
    assert data1['nome_guerra'] != data2['nome_guerra']
    assert data1['saram'] != data2['saram']


async def test_get_user_without_authentication_fails(client, users):
    """
    Testa que o endpoint requer autenticação.
    """
    user, _ = users

    response = await client.get(f'/users/{user.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_get_user_with_invalid_id_type(client, token):
    """
    Testa que passar ID inválido retorna erro de validação.
    """
    response = await client.get(
        '/users/invalid_id',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
