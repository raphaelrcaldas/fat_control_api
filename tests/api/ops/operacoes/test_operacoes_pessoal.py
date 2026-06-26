"""Testes do pessoal envolvido em Operações (`/ops/operacoes/{id}/pessoal`).

Cobre listagem, inclusão, edição e remoção, com conflitos (militar
duplicado, usuário inválido), validação de período e RBAC.
"""

from http import HTTPStatus

import pytest

from tests.factories import OperacaoFactory

pytestmark = pytest.mark.anyio


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _pessoal(user_id, **over):
    base = {
        'user_id': user_id,
        'func': 'Apoio',
        'sit': 'd',
        'data_ingresso': '2025-06-02',
        'data_regresso': '2025-06-08',
    }
    base.update(over)
    return base


@pytest.fixture
async def operacao(session, users):
    user, _ = users
    op = OperacaoFactory(created_by=user.id)
    session.add(op)
    await session.commit()
    await session.refresh(op)
    return op


async def test_list_pessoal_empty(client, operacao, org_admin_token):
    resp = await client.get(
        f'/ops/operacoes/{operacao.id}/pessoal',
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] == []


async def test_add_pessoal_success(
    client, operacao, users, org_admin_token
):
    _, other = users
    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(other.id),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['user']['id'] == other.id
    assert data['func'] == 'Apoio'
    assert data['dias'] == 7


async def test_add_pessoal_duplicate_conflict(
    client, operacao, users, org_admin_token
):
    _, other = users
    await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(other.id),
        headers=_auth(org_admin_token),
    )
    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(other.id),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.CONFLICT


async def test_add_pessoal_invalid_user_400(
    client, operacao, org_admin_token
):
    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(999999),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_add_pessoal_invalid_period_422(
    client, operacao, users, org_admin_token
):
    _, other = users
    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(
            other.id,
            data_ingresso='2025-06-08',
            data_regresso='2025-06-02',
        ),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_add_pessoal_viewer_forbidden(
    client, operacao, users, oper_viewer_token
):
    _, other = users
    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(other.id),
        headers=_auth(oper_viewer_token),
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_update_pessoal_success(
    client, operacao, users, org_admin_token
):
    _, other = users
    add = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(other.id),
        headers=_auth(org_admin_token),
    )
    pessoal_id = add.json()['data']['id']

    resp = await client.put(
        f'/ops/operacoes/{operacao.id}/pessoal/{pessoal_id}',
        json=_pessoal(other.id, func='Manutenção', sit='g'),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK

    lst = await client.get(
        f'/ops/operacoes/{operacao.id}/pessoal',
        headers=_auth(org_admin_token),
    )
    item = lst.json()['data'][0]
    assert item['func'] == 'Manutenção'
    assert item['sit'] == 'g'


async def test_update_pessoal_not_found(
    client, operacao, users, org_admin_token
):
    resp = await client.put(
        f'/ops/operacoes/{operacao.id}/pessoal/999999',
        json=_pessoal(users[1].id),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_remove_pessoal_success(
    client, operacao, users, org_admin_token
):
    _, other = users
    add = await client.post(
        f'/ops/operacoes/{operacao.id}/pessoal',
        json=_pessoal(other.id),
        headers=_auth(org_admin_token),
    )
    pessoal_id = add.json()['data']['id']

    resp = await client.delete(
        f'/ops/operacoes/{operacao.id}/pessoal/{pessoal_id}',
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK

    lst = await client.get(
        f'/ops/operacoes/{operacao.id}/pessoal',
        headers=_auth(org_admin_token),
    )
    assert lst.json()['data'] == []


async def test_remove_pessoal_not_found(
    client, operacao, org_admin_token
):
    resp = await client.delete(
        f'/ops/operacoes/{operacao.id}/pessoal/999999',
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
