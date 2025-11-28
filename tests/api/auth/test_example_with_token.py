"""Exemplo de como usar a fixture token nos testes."""

from http import HTTPStatus

import pytest

from fcontrol_api.security import create_access_token

pytestmark = pytest.mark.anyio


async def test_example_authenticated_request(client, token):
    """
    Exemplo de teste usando um token JWT.

    A fixture 'token' gera automaticamente um token válido
    para o primeiro usuário da fixture 'users'.
    """
    response = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert 'id' in data
    assert 'nome_guerra' in data


async def test_example_post_with_token(client, token, users):
    """
    Exemplo de POST com autenticação.
    """
    user, _ = users

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'user_id': user.id,  # Usa o ID real do usuário
            'date_start': '2023-03-23',
            'date_end': '2023-03-24',
            'mtv': 'teste_teste',
            'obs': 'obs_obs',
        },
    )

    # O status pode variar dependendo da validação
    assert response.status_code == HTTPStatus.CREATED


async def test_example_without_token_fails(client):
    """
    Exemplo de requisição sem token que deve falhar.
    """
    response = await client.get('/users/me')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_example_with_fatcontrol_client(client, users, make_token):
    """
    Exemplo de uso com cliente 'fatcontrol'.

    O make_token garante automaticamente que o usuário
    tenha uma role antes de criar o token (requisito Zero Trust).
    """
    user, _ = users

    # Cria token para cliente fatcontrol (requer role por Zero Trust)
    fatcontrol_token = await make_token(user, client_id='fatcontrol')

    response = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {fatcontrol_token}'},
    )

    assert response.status_code == HTTPStatus.OK


async def test_example_with_different_users(client, users, make_token):
    """
    Exemplo testando com múltiplos usuários.
    """
    user1, user2 = users

    # Token para usuário 1
    token1 = await make_token(user1)

    # Token para usuário 2
    token2 = await make_token(user2)

    # Cada usuário acessa seus próprios dados
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

    # Verifica que são usuários diferentes
    assert response1.json()['id'] != response2.json()['id']


async def test_token_without_user_id_fails(client, users):
    """
    Testa que um token sem user_id é rejeitado.

    O middleware valida que o campo 'user_id' está presente no token.
    Tokens sem este campo devem retornar 401 com mensagem apropriada.
    """
    user, _ = users

    # Cria token sem user_id (apenas app_client)
    data = {
        'sub': 'Test User',
        'app_client': 'test-client',
        # user_id ausente intencionalmente
    }
    invalid_token = create_access_token(data=data)

    response = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {invalid_token}'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.text == 'Token inválido ou expirado.'


async def test_token_without_app_client_fails(client, users):
    """
    Testa que um token sem app_client é rejeitado.

    O middleware valida que o campo 'app_client' está presente no token.
    Tokens sem este campo devem retornar 401 com mensagem apropriada.
    """
    user, _ = users

    # Cria token sem app_client (apenas user_id)
    data = {
        'sub': 'Test User',
        'user_id': user.id,
        # app_client ausente intencionalmente
    }
    invalid_token = create_access_token(data=data)

    response = await client.get(
        '/users/me',
        headers={'Authorization': f'Bearer {invalid_token}'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.text == 'Token inválido ou expirado.'
