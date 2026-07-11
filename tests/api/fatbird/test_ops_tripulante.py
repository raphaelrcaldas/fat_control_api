"""Quadrinhos e SEBO no FatBird (quads.ts, sebo.ts).

São telas operacionais da tripulação: o militar vê o quadro de sobrevoo
da sua unidade e o próprio quadrinho. Nenhuma dessas rotas é gateada por
permissão (o tripulante não tem role), então o que precisa valer é o
escopo de organização.
"""

from http import HTTPStatus

import pytest

from tests.api.fatbird.conftest import auth
from tests.factories import QuadFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def trip_1gt(session):
    """Um tripulante de OUTRA organização, para as sondas cross-org."""
    user = UserFactory(unidade='1gt')
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae='1gt', active=True)
    session.add(trip)
    await session.commit()
    return trip


# ── Quadrinhos ─────────────────────────────────────────────────────


async def test_lista_quads_da_propria_org(client, trip_user, trip_token):
    """O quadro da unidade abre para o tripulante (sem role)."""
    _, trip = trip_user

    resp = await client.get(
        '/ops/quads/',
        params={'tipo_quad': 1, 'funcao': trip.func, 'proj': trip.proj},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK


async def test_lista_tipos_de_quad(client, trip_token):
    """Os tipos de quadrinho da org ativa abrem para o tripulante."""
    resp = await client.get('/ops/quads/types', headers=auth(trip_token))

    assert resp.status_code == HTTPStatus.OK


async def test_le_o_proprio_quadrinho(client, session, trip_user, trip_token):
    """O tripulante lê o próprio quadrinho por trip_id."""
    _, trip = trip_user
    quad = QuadFactory(trip_id=trip.id, type_id=1)
    session.add(quad)
    await session.commit()

    resp = await client.get(
        f'/ops/quads/trip/{trip.id}',
        params={'type_id': 1},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
    ids = {q['id'] for q in resp.json()['data']}
    assert quad.id in ids


async def test_nao_le_quadrinho_de_outra_org(
    client, session, trip_token, trip_1gt
):
    """O quadrinho de tripulante de OUTRA org não vaza (escopo por uae)."""
    quad = QuadFactory(trip_id=trip_1gt.id, type_id=1)
    session.add(quad)
    await session.commit()

    resp = await client.get(
        f'/ops/quads/trip/{trip_1gt.id}',
        params={'type_id': 1},
        headers=auth(trip_token),
    )

    ids = {q['id'] for q in resp.json()['data']} if resp.is_success else set()
    assert quad.id not in ids, (
        'quadrinho de tripulante da 1gt vazou para o token da 11gt'
    )


# ── SEBO ───────────────────────────────────────────────────────────


async def test_sebo_da_propria_org(client, trip_user, trip_token):
    """O SEBO da unidade abre para o tripulante (sem role)."""
    _, trip = trip_user

    resp = await client.get(
        '/estatistica/sebo/',
        params={'func': trip.func},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
