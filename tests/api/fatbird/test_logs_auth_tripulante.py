"""Histórico de ações e ciclo do token no FatBird (logs.ts, auth.ts).

O portal mostra ao militar o próprio histórico de ações e mantém a sessão
viva com `refresh_token` / `switch-org`. Nada disso pode exigir role.
"""

from http import HTTPStatus

import pytest

from tests.api.fatbird.conftest import auth
from tests.factories import UserActionLogFactory

pytestmark = pytest.mark.anyio


# ── Logs ───────────────────────────────────────────────────────────


async def test_le_o_proprio_historico(client, session, trip_user, trip_token):
    """O militar vê as próprias ações sem a permissão de logs."""
    user, _ = trip_user
    log = UserActionLogFactory(user_id=user.id, action='update')
    session.add(log)
    await session.commit()

    resp = await client.get(
        '/logs/user-actions',
        params={'user_id': user.id},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
    ids = {item['id'] for item in resp.json()['data']}
    assert log.id in ids


# ── Auth (ciclo do token) ──────────────────────────────────────────


async def test_refresh_do_proprio_token(client, trip_token):
    """O portal renova o token do tripulante (sem role)."""
    resp = await client.post(
        '/auth/refresh_token', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['access_token']


async def test_switch_org_para_a_propria_unidade(client, trip_token):
    """O OrgSwitcher do portal troca para a unidade do próprio militar."""
    resp = await client.post(
        '/auth/switch-org',
        json={'organizacao_id': '11gt'},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['access_token']


async def test_switch_org_para_unidade_alheia_e_negado(client, trip_token):
    """O tripulante não troca para uma org onde não tem vínculo."""
    resp = await client.post(
        '/auth/switch-org',
        json={'organizacao_id': '1gt'},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN
