"""
Testes para o endpoint POST /users/reset-pwd.

Este endpoint permite que um administrador resete a senha
de um usuário para a senha padrão.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.users import User
from fcontrol_api.security import verify_password
from fcontrol_api.settings import Settings

pytestmark = pytest.mark.anyio


async def test_reset_pwd_success(client, token, users, session):
    """
    Testa que um administrador pode resetar a senha de um usuário.
    """
    user, other_user = users

    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {'detail': 'Senha resetada com sucesso!'}

    # Verifica que a senha foi resetada para a senha padrão
    await session.refresh(other_user)
    db_user = await session.scalar(
        select(User).where(User.id == other_user.id)
    )

    assert db_user is not None
    default_password = Settings().DEFAULT_USER_PASSWORD
    assert verify_password(default_password, db_user.password)
    assert db_user.first_login is True


async def test_reset_pwd_sets_first_login_flag(client, token, users, session):
    """
    Testa que o flag first_login é setado para True.
    """
    user, other_user = users
    other_user.first_login = False
    await session.commit()

    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que first_login foi setado
    await session.refresh(other_user)
    assert other_user.first_login is True


async def test_reset_pwd_user_not_found(client, token):
    """
    Testa que resetar senha de usuário inexistente retorna erro.
    """
    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': 99999},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'User not found'}


async def test_reset_pwd_without_token_fails(client, users):
    """
    Testa que requisição sem token é rejeitada.
    """
    _, other_user = users

    response = await client.post(
        '/users/reset-pwd',
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_reset_pwd_with_invalid_token_fails(client, users):
    """
    Testa que requisição com token inválido é rejeitada.
    """
    _, other_user = users

    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': 'Bearer invalid-token'},
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_reset_pwd_without_user_id_fails(client, token):
    """
    Testa que requisição sem user_id é rejeitada.
    """
    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
