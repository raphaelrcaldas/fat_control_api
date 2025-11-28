import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.auth import OAuth2AuthorizationCode
from fcontrol_api.models.security.resources import UserRole
from tests.api.conftest import generate_pkce_pair
from tests.factories import OAuth2ClientFactory

pytestmark = pytest.mark.anyio


async def test_exchange_code_success(client, auth_code_data):
    """Testa troca bem-sucedida de código por token"""
    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert 'access_token' in data
    assert data['token_type'] == 'bearer'
    assert 'first_login' in data
    assert isinstance(data['access_token'], str)
    assert len(data['access_token']) > 0


async def test_exchange_code_invalid_grant_type(client, auth_code_data):
    """Testa falha com grant_type inválido"""
    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'client_credentials',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Unsupported grant_type'}


async def test_exchange_code_missing_pkce_cookie(client, auth_code_data):
    """Testa falha quando cookie pkce_code_verifier não está presente"""
    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        # Sem o cookie pkce_code_verifier
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'PKCE code verifier cookie not found.'
    }


async def test_exchange_code_invalid_code(client, oauth_client):
    """Testa falha com código de autorização inválido"""
    code_verifier, _ = generate_pkce_pair()

    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': 'invalid-code-12345',
            'redirect_uri': oauth_client.redirect_uri,
            'client_id': oauth_client.client_id,
        },
        cookies={'pkce_code_verifier': code_verifier},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Invalid authorization code'}


async def test_exchange_code_client_id_mismatch(
    client, auth_code_data, session
):
    """Testa falha quando client_id não corresponde"""
    # Cria outro cliente

    other_client = OAuth2ClientFactory(
        client_id='other-client', redirect_uri='http://localhost:3000/callback'
    )
    session.add(other_client)
    await session.commit()

    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': other_client.client_id,  # Client diferente
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Client ID mismatch'}


async def test_exchange_code_redirect_uri_mismatch(client, auth_code_data):
    """Testa falha quando redirect_uri não corresponde"""
    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': 'http://evil.com/callback',  # URI diferente
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Redirect URI mismatch'}


async def test_exchange_code_expired(client, users, oauth_client, session):
    """Testa falha com código de autorização expirado"""
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Adiciona role para o usuário
    user_role = UserRole(user_id=user.id, role_id=1)
    session.add(user_role)
    await session.commit()

    # Cria código expirado (expira no passado)
    auth_code = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    expired_auth_code = OAuth2AuthorizationCode(
        code=auth_code,
        user_id=user.id,
        client_id=oauth_client.id,
        code_challenge=code_challenge,
        code_challenge_method='S256',
        expires_at=expires_at,
    )

    session.add(expired_auth_code)
    await session.commit()

    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': oauth_client.redirect_uri,
            'client_id': oauth_client.client_id,
        },
        cookies={'pkce_code_verifier': code_verifier},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Authorization code expired'}


async def test_exchange_code_invalid_pkce_verifier(client, auth_code_data):
    """Testa falha com code_verifier PKCE inválido"""
    # Gera um verifier diferente do usado no challenge
    wrong_verifier, _ = generate_pkce_pair()

    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': wrong_verifier},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Invalid code_verifier'}


async def test_exchange_code_invalidates_code(client, auth_code_data, session):
    """Testa se o código de autorização é invalidado após uso"""
    response = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica se o código foi deletado do banco
    db_code = await session.scalar(
        select(OAuth2AuthorizationCode).where(
            OAuth2AuthorizationCode.code == auth_code_data['code']
        )
    )

    assert db_code is None


async def test_exchange_code_cannot_reuse_code(client, auth_code_data):
    """Testa que não é possível reutilizar um código de autorização"""
    # Primeira tentativa (sucesso)
    response1 = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response1.status_code == HTTPStatus.OK

    # Segunda tentativa com o mesmo código (deve falhar)
    response2 = await client.post(
        '/auth/token',
        data={
            'grant_type': 'authorization_code',
            'code': auth_code_data['code'],
            'redirect_uri': auth_code_data['client'].redirect_uri,
            'client_id': auth_code_data['client'].client_id,
        },
        cookies={'pkce_code_verifier': auth_code_data['code_verifier']},
    )

    assert response2.status_code == HTTPStatus.BAD_REQUEST
    assert response2.json() == {'detail': 'Invalid authorization code'}
