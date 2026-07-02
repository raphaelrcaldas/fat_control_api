"""Testes de CRUD de Operações (`/ops/operacoes`).

Cobre listagem (filtros + contadores), criação, detalhe, edição e exclusão,
com escopo multi-tenant por org ativa, RBAC (view/create/delete) e
validações de período/unicidade.
"""

from datetime import date
from http import HTTPStatus

import pytest

from tests.factories import OperacaoFactory

pytestmark = pytest.mark.anyio

BASE = '/ops/operacoes/'


def _payload(**over):
    base = {
        'nome': 'Operação Alfa',
        'tipo': 'operacao',
        'cidade_id': 5300108,
        'data_inicio': '2025-06-01',
        'data_fim': '2025-06-10',
        'status': 'planejada',
    }
    base.update(over)
    return base


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


# --------------------------------------------------------------------------- #
# Listagem
# --------------------------------------------------------------------------- #
async def test_list_empty(client, org_admin_token):
    resp = await client.get(BASE, headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()['data']
    assert body['items'] == []
    assert body['counts']['todas'] == 0


async def test_list_returns_items_with_counts(
    client, session, users, org_admin_token
):
    user, _ = users
    session.add_all([
        OperacaoFactory(created_by=user.id, status='planejada'),
        OperacaoFactory(created_by=user.id, status='andamento'),
        OperacaoFactory(created_by=user.id, status='andamento'),
    ])
    await session.commit()

    resp = await client.get(BASE, headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()['data']
    assert len(body['items']) == 3
    assert body['counts']['todas'] == 3
    assert body['counts']['andamento'] == 2
    assert body['counts']['planejada'] == 1
    # Sem etapas associadas, agregados zerados
    assert all(i['horas'] == 0 and i['etapas'] == 0 for i in body['items'])


async def test_list_filter_status(client, session, users, org_admin_token):
    user, _ = users
    session.add_all([
        OperacaoFactory(created_by=user.id, status='planejada'),
        OperacaoFactory(created_by=user.id, status='encerrada'),
    ])
    await session.commit()

    resp = await client.get(
        BASE, params={'status': 'encerrada'}, headers=_auth(org_admin_token)
    )
    items = resp.json()['data']['items']
    assert len(items) == 1
    assert items[0]['status'] == 'encerrada'
    # counts são independentes do filtro de status
    assert resp.json()['data']['counts']['todas'] == 2


async def test_list_filter_tipo(client, session, users, org_admin_token):
    user, _ = users
    session.add_all([
        OperacaoFactory(created_by=user.id, tipo='manobra'),
        OperacaoFactory(created_by=user.id, tipo='exercicio'),
    ])
    await session.commit()

    resp = await client.get(
        BASE, params={'tipo': 'manobra'}, headers=_auth(org_admin_token)
    )
    items = resp.json()['data']['items']
    assert len(items) == 1
    assert items[0]['tipo'] == 'manobra'


async def test_list_filter_busca(client, session, users, org_admin_token):
    user, _ = users
    session.add_all([
        OperacaoFactory(created_by=user.id, nome='Operação Singular'),
        OperacaoFactory(created_by=user.id, nome='Outra Coisa'),
    ])
    await session.commit()

    resp = await client.get(
        BASE, params={'q': 'Singular'}, headers=_auth(org_admin_token)
    )
    items = resp.json()['data']['items']
    assert len(items) == 1
    assert items[0]['nome'] == 'Operação Singular'


async def test_list_filter_date_overlap(
    client, session, users, org_admin_token
):
    user, _ = users
    session.add_all([
        OperacaoFactory(
            created_by=user.id,
            data_inicio=date(2025, 6, 1),
            data_fim=date(2025, 6, 10),
        ),
        OperacaoFactory(
            created_by=user.id,
            data_inicio=date(2025, 1, 1),
            data_fim=date(2025, 1, 5),
        ),
    ])
    await session.commit()

    resp = await client.get(
        BASE,
        params={'date_start': '2025-05-01', 'date_end': '2025-07-01'},
        headers=_auth(org_admin_token),
    )
    items = resp.json()['data']['items']
    assert len(items) == 1
    assert items[0]['data_inicio'] == '2025-06-01'


async def test_list_scoped_by_active_org(
    client, session, users, org_admin_token
):
    """Lista só operações da org ativa ('11gt'), não de outra unidade."""
    user, _ = users
    session.add_all([
        OperacaoFactory(created_by=user.id, uae='11gt'),
        OperacaoFactory(created_by=user.id, uae='1gt'),
    ])
    await session.commit()

    resp = await client.get(BASE, headers=_auth(org_admin_token))
    items = resp.json()['data']['items']
    assert len(items) == 1


async def test_list_viewer_allowed(client, oper_viewer_token):
    resp = await client.get(BASE, headers=_auth(oper_viewer_token))
    assert resp.status_code == HTTPStatus.OK


async def test_list_without_permission_forbidden(client, org_token):
    """org_token (admin de Sistema) não tem operacoes.view em '11gt'."""
    resp = await client.get(BASE, headers=_auth(org_token))
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_list_missing_active_org(client, token):
    resp = await client.get(BASE, headers=_auth(token))
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_list_requires_auth(client):
    resp = await client.get(BASE)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# --------------------------------------------------------------------------- #
# Criação
# --------------------------------------------------------------------------- #
async def test_create_success(client, org_admin_token):
    resp = await client.post(
        BASE, json=_payload(), headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['nome'] == 'Operação Alfa'
    assert data['numero'] == 1
    assert data['dias'] == 10
    assert data['horas'] == 0


async def test_create_numero_sequential(client, org_admin_token):
    r1 = await client.post(
        BASE, json=_payload(nome='Um'), headers=_auth(org_admin_token)
    )
    r2 = await client.post(
        BASE, json=_payload(nome='Dois'), headers=_auth(org_admin_token)
    )
    assert r1.json()['data']['numero'] == 1
    assert r2.json()['data']['numero'] == 2


async def test_create_writer_allowed(client, oper_writer_token):
    resp = await client.post(
        BASE, json=_payload(), headers=_auth(oper_writer_token)
    )
    assert resp.status_code == HTTPStatus.CREATED


async def test_create_viewer_forbidden(client, oper_viewer_token):
    """Quem só tem view não cria (falta operacoes.create)."""
    resp = await client.post(
        BASE, json=_payload(), headers=_auth(oper_viewer_token)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_create_missing_active_org(client, token):
    resp = await client.post(BASE, json=_payload(), headers=_auth(token))
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_create_duplicate_nome_conflict(client, org_admin_token):
    await client.post(
        BASE, json=_payload(nome='Repetida'), headers=_auth(org_admin_token)
    )
    resp = await client.post(
        BASE, json=_payload(nome='Repetida'), headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.CONFLICT


async def test_create_invalid_period_422(client, org_admin_token):
    resp = await client.post(
        BASE,
        json=_payload(data_inicio='2025-06-10', data_fim='2025-06-01'),
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# --------------------------------------------------------------------------- #
# Detalhe
# --------------------------------------------------------------------------- #
async def test_get_detail_success(client, session, users, org_admin_token):
    user, _ = users
    op = OperacaoFactory(created_by=user.id)
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.get(f'{BASE}{op.id}', headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['id'] == op.id
    assert data['kpis']['horas'] == 0
    assert data['kpis']['etapas'] == 0
    assert data['sebo'] == []


async def test_get_detail_not_found(client, org_admin_token):
    resp = await client.get(f'{BASE}999999', headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_get_detail_cross_org_404(
    client, session, users, org_admin_token
):
    user, _ = users
    op = OperacaoFactory(created_by=user.id, uae='1gt')
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.get(f'{BASE}{op.id}', headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


# --------------------------------------------------------------------------- #
# Edição
# --------------------------------------------------------------------------- #
async def test_update_success(client, session, users, org_admin_token):
    user, _ = users
    op = OperacaoFactory(created_by=user.id, status='planejada')
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.put(
        f'{BASE}{op.id}',
        json={'nome': 'Renomeada', 'status': 'andamento'},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK

    get_resp = await client.get(
        f'{BASE}{op.id}', headers=_auth(org_admin_token)
    )
    assert get_resp.json()['data']['nome'] == 'Renomeada'
    assert get_resp.json()['data']['status'] == 'andamento'


async def test_update_not_found(client, org_admin_token):
    resp = await client.put(
        f'{BASE}999999',
        json={'nome': 'X'},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_update_invalid_period_400(
    client, session, users, org_admin_token
):
    user, _ = users
    op = OperacaoFactory(
        created_by=user.id,
        data_inicio=date(2025, 6, 1),
        data_fim=date(2025, 6, 10),
    )
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.put(
        f'{BASE}{op.id}',
        json={'data_fim': '2025-05-01'},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_update_explicit_null_422(
    client, session, users, org_admin_token
):
    """`null` explícito em coluna NOT NULL é barrado pelo schema (422)."""
    user, _ = users
    op = OperacaoFactory(created_by=user.id)
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.put(
        f'{BASE}{op.id}',
        json={'nome': None},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_viewer_forbidden(
    client, session, users, oper_viewer_token
):
    user, _ = users
    op = OperacaoFactory(created_by=user.id)
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.put(
        f'{BASE}{op.id}',
        json={'nome': 'X'},
        headers=_auth(oper_viewer_token),
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


# --------------------------------------------------------------------------- #
# Exclusão
# --------------------------------------------------------------------------- #
async def test_delete_success(client, session, users, org_admin_token):
    user, _ = users
    op = OperacaoFactory(created_by=user.id)
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.delete(
        f'{BASE}{op.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.OK

    get_resp = await client.get(
        f'{BASE}{op.id}', headers=_auth(org_admin_token)
    )
    assert get_resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_writer_without_delete_perm_forbidden(
    client, session, users, oper_writer_token
):
    """Writer tem create/view mas NÃO operacoes.delete → 403.

    Prova que a exclusão é gateada separadamente do resto das escritas.
    """
    user, _ = users
    op = OperacaoFactory(created_by=user.id)
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.delete(
        f'{BASE}{op.id}', headers=_auth(oper_writer_token)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_delete_not_found(client, org_admin_token):
    resp = await client.delete(f'{BASE}999999', headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, session, users, org_admin_token):
    user, _ = users
    op = OperacaoFactory(created_by=user.id, uae='1gt')
    session.add(op)
    await session.commit()
    await session.refresh(op)

    resp = await client.delete(
        f'{BASE}{op.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
