"""
Testes para o endpoint POST /users/reset-pwd.

Este endpoint permite que um administrador resete a senha
de um usuário para a senha padrão.
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.users import User
from fcontrol_api.security import verify_password
from fcontrol_api.settings import Settings
from tests.factories import UserFactory

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
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == 'Senha resetada com sucesso'

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

    log = await session.scalar(
        select(UserActionLog)
        .where(
            UserActionLog.resource == 'users',
            UserActionLog.resource_id == other_user.id,
            UserActionLog.action == 'reset-pwd',
        )
        .order_by(UserActionLog.id.desc())
    )

    assert log is not None
    assert json.loads(log.before) == {'first_login': False}
    assert json.loads(log.after) == {'first_login': True}
    assert 'password' not in log.before
    assert 'password' not in log.after


async def test_reset_pwd_already_first_login_no_change_log(
    client, token, users, session
):
    """Resetar quem já está em first_login=True não é uma transição.

    O handler só considera "mudança" quando `first_login_before is not
    True`; sem transição, o log 'reset-pwd' é gravado com before e after
    None — em vez de repetir {'first_login': True} nos dois lados.
    """
    _, other_user = users
    assert other_user.first_login is True

    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.OK

    log = await session.scalar(
        select(UserActionLog)
        .where(
            UserActionLog.resource == 'users',
            UserActionLog.resource_id == other_user.id,
            UserActionLog.action == 'reset-pwd',
        )
        .order_by(UserActionLog.id.desc())
    )

    assert log is not None
    assert log.before is None
    assert log.after is None


async def test_reset_pwd_non_admin_with_update_permission_scope_forbidden(
    client, users, user_with_update_permission, make_org_token
):
    """`users.update` não basta: reset-pwd exige o vínculo admin da org.

    `require_admin` (a dependência da rota) checa a role, não a permissão
    de recurso — um usuário com `users.update` mas sem a role admin recebe
    o mesmo SCOPE_FORBIDDEN de quem não tem permissão nenhuma.
    """
    _, other_user = users
    token = await make_org_token(user_with_update_permission)

    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()['message'] == 'SCOPE_FORBIDDEN'


async def test_reset_pwd_cross_org_404_matches_not_found(
    client, token, session
):
    """Admin da '11gt' resetando usuário da '1gt' recebe 404.

    `_ensure_user_in_active_org` devolve o mesmo 404 de um id inexistente
    — de propósito, para não virar oráculo de enumeração entre orgs. O
    teste compara os dois corpos de resposta (exceto o timestamp, que varia
    por natureza) em vez de só conferir o status.
    """
    other_org_user = UserFactory(unidade='1gt')
    session.add(other_org_user)
    await session.commit()
    await session.refresh(other_org_user)

    cross_org_response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': other_org_user.id},
    )
    not_found_response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': 99999},
    )

    assert cross_org_response.status_code == HTTPStatus.NOT_FOUND
    assert not_found_response.status_code == HTTPStatus.NOT_FOUND

    cross_org_body = cross_org_response.json()
    not_found_body = not_found_response.json()
    for key in ('status', 'message', 'errors', 'path'):
        assert cross_org_body[key] == not_found_body[key]


async def test_reset_pwd_token_sistema_resets_any_user(
    client, token_sistema, users
):
    """Admin de sistema reseta usuário de qualquer org — guarda intencional.

    `token_sistema` não tem `active_org`, então `_ensure_user_in_active_org`
    não restringe o alvo por unidade (mesmo padrão de `get_users`/`GET
    /users/{id}` para o contexto Sistema). Este teste é uma guarda: se um
    dia o escopo passar a exigir org também no contexto Sistema, ele deve
    virar vermelho.
    """
    _, other_user = users

    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token_sistema}'},
        params={'user_id': other_user.id},
    )

    assert response.status_code == HTTPStatus.OK


async def test_reset_pwd_user_not_found(client, token):
    """Resetar senha de usuário inexistente responde 404.

    É o mesmo status do guard de org: um usuário de outra unidade também
    responde 404. Igualar os dois é proposital — um 400 aqui distinguiria
    "não existe" de "existe em outra org" e viraria oráculo de enumeração.
    """
    response = await client.post(
        '/users/reset-pwd',
        headers={'Authorization': f'Bearer {token}'},
        params={'user_id': 99999},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'não encontrado' in resp['message'].lower()


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
