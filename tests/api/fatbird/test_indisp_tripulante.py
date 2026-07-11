"""Indisponibilidade pelo FatBird: o tripulante gere só a DELE.

É a função central do portal: o tripulante lança/edita/remove a própria
indisponibilidade **sem ter role**. Antes, os handlers de escrita
buscavam a indisp só pelo `id` e não checavam nada — qualquer tripulante
podia editar/apagar a de qualquer militar, de qualquer organização (IDOR).
Agora vale owner-OR-permission ('indisp_trips') + escopo por
`Tripulante.uae`.

A leitura segue aberta dentro da org (a lista de tripulação já mostra as
indisponibilidades de todos), só barrando cross-org.
"""

from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.indisp import Indisp
from tests.api.fatbird.conftest import auth

pytestmark = pytest.mark.anyio

URL = '/indisp/'


def _payload(user_id: int):
    return {
        'user_id': user_id,
        'date_start': '2026-08-01',
        'date_end': '2026-08-05',
        'mtv': 'fer',
        'obs': 'teste',
    }


async def _mk_indisp(session, user_id: int, created_by: int):
    indisp = Indisp(
        user_id=user_id,
        date_start=date(2026, 9, 1),
        date_end=date(2026, 9, 5),
        mtv='fer',
        obs='existente',
        created_by=created_by,
    )
    session.add(indisp)
    await session.commit()
    return indisp


# ── Self-service (tem de funcionar sem role) ───────────────────────


async def test_cria_a_propria(client, trip_user, trip_token):
    """O tripulante lança a própria indisponibilidade sem ter role."""
    user, _ = trip_user
    resp = await client.post(
        URL, json=_payload(user.id), headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.CREATED


async def test_edita_a_propria(client, session, trip_user, trip_token):
    user, _ = trip_user
    indisp = await _mk_indisp(session, user.id, created_by=user.id)

    resp = await client.put(
        f'{URL}{indisp.id}',
        json={'obs': 'editado pelo dono'},
        headers=auth(trip_token),
    )
    assert resp.status_code == HTTPStatus.OK


async def test_remove_a_propria(client, session, trip_user, trip_token):
    user, _ = trip_user
    indisp = await _mk_indisp(session, user.id, created_by=user.id)

    resp = await client.delete(f'{URL}{indisp.id}', headers=auth(trip_token))
    assert resp.status_code == HTTPStatus.OK


# ── IDOR: não pode mexer na de outro militar ───────────────────────


async def test_nao_cria_para_outro(client, trip_token, outro_trip):
    """Sem 'indisp_trips.create', não lança indisp em nome de outro."""
    outro, _ = outro_trip
    resp = await client.post(
        URL, json=_payload(outro.id), headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_nao_edita_a_de_outro(client, session, trip_token, outro_trip):
    """Sem 'indisp_trips.update', não edita a indisp de outro militar."""
    outro, _ = outro_trip
    indisp = await _mk_indisp(session, outro.id, created_by=outro.id)

    resp = await client.put(
        f'{URL}{indisp.id}',
        json={'obs': 'invadido'},
        headers=auth(trip_token),
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_nao_remove_a_de_outro(client, session, trip_token, outro_trip):
    """Sem 'indisp_trips.delete', não remove a indisp de outro militar."""
    outro, _ = outro_trip
    indisp = await _mk_indisp(session, outro.id, created_by=outro.id)
    indisp_id = indisp.id

    resp = await client.delete(f'{URL}{indisp_id}', headers=auth(trip_token))
    assert resp.status_code == HTTPStatus.FORBIDDEN

    # E continua ativa (soft delete não foi aplicado).
    session.expire_all()
    db = await session.get(Indisp, indisp_id)
    assert db.deleted_at is None
