"""
Fixtures compartilhadas entre todos os testes de API.

Este conftest.py contém fixtures usadas por múltiplos testes de endpoints:
- users: Dois usuários de teste (user com senha, other_user)
- client: Cliente HTTP para testar endpoints
- oauth_client: Cliente OAuth2 para testes de autenticação
- token: Token JWT genérico para endpoints autenticados
- make_token: Factory para criar tokens customizados
- generate_pkce_pair: Helper para gerar pares PKCE em testes OAuth2
"""

import base64
import hashlib
import secrets

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.app import app
from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.security import create_access_token, get_password_hash
from tests.factories import OAuth2ClientFactory, UserFactory


@pytest.fixture
async def client(session):
    """
    Cliente HTTP assíncrono para testar endpoints da API.
    """

    def get_session_override():
        return session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://127.0.0.1:8000/'
    ) as client:
        app.dependency_overrides[get_session] = get_session_override

        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def users(session):
    """
    Cria dois usuários de teste no banco de dados.

    O primeiro usuário tem uma senha conhecida para testes de autenticação.
    O segundo usuário é usado para testes que requerem múltiplos usuários
    (ex: autorização, isolamento de dados).

    Uso:
        async def test_with_users(users):
            user, other_user = users
            assert user.saram != other_user.saram

        async def test_login(client, users):
            user, _ = users
            response = await client.post('/auth/login', json={
                'saram': user.saram,
                'password': user.clean_password  # 'testtest'
            })

    Returns:
        tuple: (user, other_user)
            - user: Usuário com senha conhecida (user.clean_password)
            - other_user: Segundo usuário para testes multi-user
    """
    password = 'testtest'

    user = UserFactory(password=get_password_hash(password))
    other_user = UserFactory()

    db_users = [user, other_user]

    session.add_all(db_users)
    await session.commit()

    for instance in db_users:
        await session.refresh(instance)

    user.clean_password = password

    return (user, other_user)


@pytest.fixture
async def oauth_client(session):
    """
    Cria um cliente OAuth2 para testes de autenticação.

    Configuração padrão:
    - client_id: 'test-client'
    - redirect_uri: 'http://localhost:3000/callback'

    Uso:
        async def test_oauth(oauth_client):
            assert oauth_client.client_id == 'test-client'
    """
    client = OAuth2ClientFactory(
        client_id='test-client', redirect_uri='http://localhost:3000/callback'
    )

    session.add(client)
    await session.commit()
    await session.refresh(client)

    return client


@pytest.fixture
async def token(users, session):
    """
    Gera um token JWT válido para o primeiro usuário da fixture 'users'.
    Garante que o usuário tenha uma role (requisito Zero Trust).

    Uso:
        async def test_protected_endpoint(client, token):
            response = await client.get(
                '/endpoint',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code == 200

    Returns:
        str: Token JWT válido para uso em testes
    """

    user, _ = users

    # Garante que o usuário tem uma role (requisito Zero Trust)
    existing_role = await session.scalar(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    if not existing_role:
        user_role = UserRole(user_id=user.id, role_id=1)
        session.add(user_role)
        await session.commit()

    # Recarrega o usuário com a relação posto
    db_user = await session.scalar(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.posto))
    )

    # Gera o token diretamente usando as funções de segurança
    data = {
        'sub': f'{db_user.posto.short} {db_user.nome_guerra}',
        'user_id': db_user.id,
        'app_client': 'test-client',
    }
    access_token = create_access_token(data=data)

    return access_token


@pytest.fixture
def make_token(session):
    """
    Factory fixture para criar tokens JWT customizados.
    Garante que o usuário tenha uma role quando necessário (Zero Trust).

    Uso:
        async def test_with_custom_token(client, users, make_token):
            user, _ = users
            custom_token = await make_token(user, client_id='fatcontrol')
            response = await client.get(
                '/endpoint',
                headers={'Authorization': f'Bearer {custom_token}'}
            )

    Args:
        user: Objeto User para o qual criar o token
        client_id: ID do cliente OAuth2 (default: 'test-client')
        ensure_role: Se True, garante que usuário tem role (default: True)

    Returns:
        Callable: Função assíncrona que retorna um token JWT
    """

    async def _make_token(user, client_id='test-client', ensure_role=True):
        # Para clientes que requerem role, garante que existe
        if ensure_role:
            existing_role = await session.scalar(
                select(UserRole).where(UserRole.user_id == user.id)
            )
            if not existing_role:
                user_role = UserRole(user_id=user.id, role_id=1)
                session.add(user_role)
                await session.commit()

        # Recarrega o usuário com a relação posto
        db_user = await session.scalar(
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.posto))
        )

        data = {
            'sub': f'{db_user.posto.short} {db_user.nome_guerra}',
            'user_id': db_user.id,
            'app_client': client_id,
        }
        return create_access_token(data=data)

    return _make_token


def generate_pkce_pair():
    """
    Gera um par code_verifier e code_challenge para PKCE (OAuth2).

    PKCE (Proof Key for Code Exchange) é uma extensão de segurança do OAuth2
    que previne ataques de interceptação de código de autorização.

    Uso:
        code_verifier, code_challenge = generate_pkce_pair()

        # Use code_challenge na requisição de autorização
        # Use code_verifier na troca do código por token

    Returns:
        tuple: (code_verifier: str, code_challenge: str)
    """
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(
        b'='
    )
    sha256_hash = hashlib.sha256(code_verifier).digest()
    code_challenge = base64.urlsafe_b64encode(sha256_hash).rstrip(b'=')
    return code_verifier.decode(), code_challenge.decode()
