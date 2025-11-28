"""
Fixtures específicas para testes de autenticação OAuth2.
"""

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from fcontrol_api.models.security.auth import OAuth2AuthorizationCode
from fcontrol_api.models.security.resources import UserRole
from tests.api.conftest import generate_pkce_pair


@pytest.fixture
async def auth_code_data(users, oauth_client, session):
    """
    Cria um código de autorização OAuth2 válido no banco de dados.

    Esta fixture é usada para testar o endpoint de troca de código por token
    (token exchange). Ela cria todos os dados necessários incluindo:
    - Código de autorização válido
    - PKCE code_verifier e code_challenge
    - Associação com usuário e cliente OAuth2
    - Role para o usuário (requisito Zero Trust)

    Uso:
        async def test_token_exchange(client, auth_code_data):
            response = await client.post(
                '/auth/token',
                data={
                    'grant_type': 'authorization_code',
                    'code': auth_code_data['code'],
                    'redirect_uri': auth_code_data['client'].redirect_uri,
                    'client_id': auth_code_data['client'].client_id,
                },
                cookies={'pkce_code_verifier': auth_code_data['code_verifier']}
            )
            assert response.status_code == 200

    Returns:
        dict: Dicionário contendo:
            - code: Código de autorização
            - code_verifier: PKCE verifier para validação
            - code_challenge: PKCE challenge usado no código
            - user: Objeto User associado
            - client: Objeto OAuth2Client associado
    """
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Adiciona role para o usuário (requisito Zero Trust)
    user_role = UserRole(user_id=user.id, role_id=1)
    session.add(user_role)
    await session.commit()

    # Cria o código de autorização
    auth_code = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    new_auth_code = OAuth2AuthorizationCode(
        code=auth_code,
        user_id=user.id,
        client_id=oauth_client.id,
        code_challenge=code_challenge,
        code_challenge_method='S256',
        expires_at=expires_at,
    )

    session.add(new_auth_code)
    await session.commit()

    return {
        'code': auth_code,
        'code_verifier': code_verifier,
        'code_challenge': code_challenge,
        'user': user,
        'client': oauth_client,
    }
