"""
Testes para o endpoint DELETE /ops/om/{id} (soft delete de ordem).

Testa soft delete, idempotencia e cenarios de erro.
"""

from datetime import datetime, timezone
from http import HTTPStatus

import pytest

from tests.factories import OrdemMissaoFactory

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om'


async def test_delete_ordem_success(
    client, session, users, token
):
    """Soft delete marca deleted_at e retorna sucesso."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.delete(
        f'{BASE_URL}/{ordem.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'

    await session.refresh(ordem)
    assert ordem.deleted_at is not None


async def test_delete_ordem_not_found(
    client, session, token
):
    """Deletar ordem inexistente retorna 404."""
    response = await client.delete(
        f'{BASE_URL}/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_delete_ordem_already_deleted(
    client, session, users, token
):
    """Deletar ordem ja deletada retorna 404."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    response = await client.delete(
        f'{BASE_URL}/{ordem.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_deleted_ordem_not_in_list(
    client, session, users, token
):
    """Ordem deletada nao aparece na listagem."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    await client.delete(
        f'{BASE_URL}/{ordem.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    response = await client.get(
        '/ops/om/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    ids = [item['id'] for item in resp['data']]
    assert ordem.id not in ids


async def test_delete_ordem_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.delete(f'{BASE_URL}/1')
    assert response.status_code == HTTPStatus.UNAUTHORIZED
