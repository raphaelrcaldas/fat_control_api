"""
Testes para o endpoint GET /users/me.

Este endpoint retorna o perfil do usuário autenticado,
incluindo suas permissões e role.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_read_users_me_success(client, token):
    """
    Testa que um usuário autenticado pode acessar seu próprio perfil.
    """
    response = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    # Verifica wrapper de resposta
    assert resp['status'] == 'success'
    assert 'timestamp' in resp
    assert 'data' in resp

    data = resp['data']

    # Verifica campos obrigatórios
    assert 'id' in data
    assert 'posto' in data
    assert 'nome_guerra' in data
    assert 'role' in data
    assert 'permissions' in data

    # Verifica tipos
    assert isinstance(data['id'], int)
    assert isinstance(data['posto'], str)
    assert isinstance(data['nome_guerra'], str)
    assert isinstance(data['permissions'], list)


async def test_read_users_me_without_token_fails(client):
    """
    Testa que requisição sem token é rejeitada.
    """
    response = await client.get('/users/me')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_read_users_me_with_invalid_token_fails(client):
    """
    Testa que requisição com token inválido é rejeitada.
    """
    response = await client.get(
        '/users/me',
        headers={'Authorization': 'Bearer invalid-token'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_read_users_me_with_different_users(client, users, make_token):
    """
    Testa que cada usuário recebe seu próprio perfil.
    """
    user1, user2 = users

    token1 = await make_token(user1)
    token2 = await make_token(user2)

    response1 = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {token1}'},
    )
    response2 = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {token2}'},
    )

    assert response1.status_code == HTTPStatus.OK
    assert response2.status_code == HTTPStatus.OK

    data1 = response1.json()['data']
    data2 = response2.json()['data']

    # Verifica que são usuários diferentes
    assert data1['id'] != data2['id']
    assert data1['nome_guerra'] != data2['nome_guerra']


async def test_read_users_me_without_role_returns_none(
    client, users, make_token
):
    """
    Testa que usuário sem role cadastrada retorna role=None.

    Este teste cobre a linha 37 de fcontrol_api/services/auth.py
    onde get_user_roles retorna role_data com role=None quando
    o usuário não possui nenhuma role cadastrada.
    """
    user, _ = users
    # Cria token sem garantir role (ensure_role=False)
    token = await make_token(user, ensure_role=False)

    response = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']

    # Verifica que role é None e permissions é lista vazia
    assert data['role'] is None
    assert data['permissions'] == []
    assert data['id'] == user.id
