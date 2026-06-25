"""
Testes para o endpoint DELETE /users/{user_id}.

Este endpoint permite deletar um usuário.
Requer permissão 'user:delete' e impede auto-deleção.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.shared.users import User

pytestmark = pytest.mark.anyio


async def test_delete_user_success(
    client, session, users, user_with_delete_permission, make_token
):
    """Testa que um usuário com permissão pode deletar outro usuário."""
    token = await make_token(user_with_delete_permission)
    _, other_user = users
    other_user_id = other_user.id

    response = await client.delete(
        f'/users/{other_user_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'deletado' in resp['message'].lower()

    db_user = await session.scalar(
        select(User).where(User.id == other_user_id)
    )
    assert db_user is None


async def test_delete_user_without_permission_fails(client, users, make_token):
    """Testa que usuário sem permissão recebe 403."""
    user, other_user = users
    # ensure_role=False: sem a role default (admin), o usuário fica de fato
    # sem permissão de delete.
    token = await make_token(user, ensure_role=False)

    response = await client.delete(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_delete_user_self_deletion_fails(
    client, users, user_with_delete_permission, make_token
):
    """Testa que o usuário não pode deletar a si mesmo."""
    token = await make_token(user_with_delete_permission)

    response = await client.delete(
        f'/users/{user_with_delete_permission.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'próprio' in resp['message'].lower()


async def test_delete_user_not_found(
    client, user_with_delete_permission, make_token
):
    """Testa que deletar usuário inexistente retorna 404."""
    token = await make_token(user_with_delete_permission)

    response = await client.delete(
        '/users/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'nao encontrado' in resp['message'].lower()


async def test_delete_user_without_token_fails(client, users):
    """Testa que requisição sem token é rejeitada."""
    _, other_user = users

    response = await client.delete(f'/users/{other_user.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
