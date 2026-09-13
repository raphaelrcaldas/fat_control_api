"""
Testes para o endpoint POST /users/change-pwd.

Este endpoint permite que um usuário autenticado mude sua própria senha.
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.users import User
from fcontrol_api.security import verify_password

pytestmark = pytest.mark.anyio


async def test_change_pwd_success(client, token, users, session):
    """
    Testa que um usuário pode mudar sua própria senha com sucesso.
    """
    user, _ = users

    response = await client.post(
        '/users/change-pwd',
        headers={'Authorization': f'Bearer {token}'},
        json={'new_pwd': 'NewPass123!'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == 'Senha alterada com sucesso'

    # Verifica que a senha foi alterada no banco
    await session.refresh(user)
    db_user = await session.scalar(select(User).where(User.id == user.id))

    assert db_user is not None
    assert verify_password('NewPass123!', db_user.password)
    assert db_user.first_login is False


async def test_change_pwd_updates_first_login_flag(
    client, token, users, session
):
    """
    Testa que o flag first_login é atualizado para False.
    """
    user, _ = users
    user.first_login = True
    await session.commit()

    response = await client.post(
        '/users/change-pwd',
        headers={'Authorization': f'Bearer {token}'},
        json={'new_pwd': 'NewPass123!'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que first_login foi atualizado
    await session.refresh(user)
    assert user.first_login is False

    log = await session.scalar(
        select(UserActionLog)
        .where(
            UserActionLog.resource == 'users',
            UserActionLog.resource_id == user.id,
            UserActionLog.action == 'change-pwd',
        )
        .order_by(UserActionLog.id.desc())
    )

    assert log is not None
    assert json.loads(log.before) == {'first_login': True}
    assert json.loads(log.after) == {'first_login': False}
    assert 'password' not in log.before
    assert 'password' not in log.after


async def test_change_pwd_already_false_no_change_log(
    client, token, users, session
):
    """Trocar a senha com first_login já False não é uma transição.

    O handler só considera "mudança" quando `first_login_before is not
    False`; sem transição, o log 'change-pwd' é gravado com before e after
    None — em vez de repetir {'first_login': False} nos dois lados.
    """
    user, _ = users
    user.first_login = False
    await session.commit()

    response = await client.post(
        '/users/change-pwd',
        headers={'Authorization': f'Bearer {token}'},
        json={'new_pwd': 'NewPass123!'},
    )

    assert response.status_code == HTTPStatus.OK

    log = await session.scalar(
        select(UserActionLog)
        .where(
            UserActionLog.resource == 'users',
            UserActionLog.resource_id == user.id,
            UserActionLog.action == 'change-pwd',
        )
        .order_by(UserActionLog.id.desc())
    )

    assert log is not None
    assert log.before is None
    assert log.after is None


async def test_change_pwd_without_token_fails(client):
    """
    Testa que requisição sem token é rejeitada.
    """
    response = await client.post(
        '/users/change-pwd',
        json={'new_pwd': 'NewPass123!'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_change_pwd_with_invalid_token_fails(client):
    """
    Testa que requisição com token inválido é rejeitada.
    """
    response = await client.post(
        '/users/change-pwd',
        headers={'Authorization': 'Bearer invalid-token'},
        json={'new_pwd': 'NewPass123!'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_change_pwd_with_missing_new_pwd_fails(client, token):
    """
    Testa que requisição sem new_pwd é rejeitada.
    """
    response = await client.post(
        '/users/change-pwd',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
