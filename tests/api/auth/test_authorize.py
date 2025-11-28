from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.auth import OAuth2AuthorizationCode
from fcontrol_api.models.security.resources import UserRole
from tests.api.conftest import generate_pkce_pair

pytestmark = pytest.mark.anyio


async def test_authorize_success(client, users, oauth_client, session):
    """Testa autorização bem-sucedida com credenciais válidas"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Adiciona uma role para o usuário (necessário para validação)
    user_role = UserRole(user_id=user.id, role_id=1)
    session.add(user_role)
    await session.commit()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert 'code' in data
    assert isinstance(data['code'], str)
    assert len(data['code']) > 0


async def test_authorize_invalid_response_type(client, users, oauth_client):
    """Testa falha com response_type inválido"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'invalid',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Invalid response_type'}


async def test_authorize_invalid_code_challenge_method(
    client, users, oauth_client
):
    """Testa falha com code_challenge_method inválido"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'plain',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'code_challenge_method must be S256'}


async def test_authorize_invalid_client_id(client, users, oauth_client):
    """Testa falha com client_id inválido"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': 'invalid-client',
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Invalid client or redirect_uri'}


async def test_authorize_invalid_redirect_uri(client, users, oauth_client):
    """Testa falha com redirect_uri inválido"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': 'http://evil.com/callback',
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Invalid client or redirect_uri'}


async def test_authorize_invalid_credentials(client, users, oauth_client):
    """Testa falha com senha incorreta"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': 'wrong-password',
        },
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {'detail': 'Credenciais inválidas'}


async def test_authorize_user_not_found(client, oauth_client):
    """Testa falha com usuário inexistente"""
    code_verifier, code_challenge = generate_pkce_pair()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': 9999999,
            'password': 'any-password',
        },
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {'detail': 'Credenciais inválidas'}


async def test_authorize_inactive_user(client, users, oauth_client, session):
    """Testa falha com usuário inativo"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Desativa o usuário
    user.active = False
    await session.commit()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json() == {'detail': 'Conta inativa. Contate o suporte'}


async def test_authorize_user_without_required_permissions(
    client, users, oauth_client
):
    """Testa falha quando usuário não tem permissões mínimas para o cliente"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Modifica o client_id para 'fatcontrol' que requer roles
    oauth_client.client_id = 'fatcontrol'

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': 'fatcontrol',
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert 'sem permissões cadastradas' in response.json()['detail'].lower()


async def test_authorize_creates_valid_auth_code(
    client, users, oauth_client, session
):
    """Testa se o código de autorização é criado corretamente no banco"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Adiciona role para o usuário

    user_role = UserRole(user_id=user.id, role_id=1)
    session.add(user_role)
    await session.commit()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.OK
    auth_code = response.json()['code']

    # Verifica se o código foi salvo no banco

    db_code = await session.scalar(
        select(OAuth2AuthorizationCode).where(
            OAuth2AuthorizationCode.code == auth_code
        )
    )

    assert db_code is not None
    assert db_code.user_id == user.id
    assert db_code.client_id == oauth_client.id
    assert db_code.code_challenge == code_challenge
    assert db_code.code_challenge_method == 'S256'
