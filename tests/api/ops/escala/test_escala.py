"""Testes do endpoint GET /ops/escala/disponiveis.

Lista tripulantes elegíveis para escala numa janela de datas. Escopo por
org ativa (`Tripulante.uae`). Elegibilidade da função: `func` solicitada,
`oper != 'al'`, `proj` casando e `data_op` preenchida. O `tipo_quad_id`
precisa pertencer a um grupo elegível (sobr/nasc/local/inter).
"""

from datetime import date
from http import HTTPStatus

import pytest

from tests.factories import FuncFactory, TripFactory

pytestmark = pytest.mark.anyio

URL = '/ops/escala/disponiveis'

# QuadsType.id=1 -> group 'sobr' (elegível); id=10 -> 'desloc' (inelegível).
TIPO_ELEGIVEL = 1
TIPO_INELEGIVEL = 10


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _params(**over):
    base = {
        'date_start': '2025-06-01',
        'date_end': '2025-06-30',
        'tipo_quad_id': TIPO_ELEGIVEL,
        'funcs': ['pil'],
        'sort': 'quads_asc',
    }
    base.update(over)
    return base


async def _trip_with_func(
    session,
    user_id,
    *,
    uae='11gt',
    active=True,
    func='pil',
    oper='op',
    proj='kc-390',
    data_op=date(2025, 1, 1),
):
    trip = TripFactory(user_id=user_id, uae=uae, active=active)
    session.add(trip)
    await session.flush()
    funcao = FuncFactory(
        trip_id=trip.id,
        func=func,
        oper=oper,
        proj=proj,
        data_op=data_op,
    )
    session.add(funcao)
    await session.flush()
    return trip


def _all_trip_ids(payload):
    ids = []
    for section in payload['sections']:
        ids.extend(t['id'] for t in section['trips'])
    return ids


async def test_returns_eligible_trip(client, session, users, org_token):
    user, _ = users
    trip = await _trip_with_func(session, user.id)
    await session.commit()

    resp = await client.get(URL, params=_params(), headers=_auth(org_token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert [s['func'] for s in data['sections']] == ['pil']
    assert trip.id in _all_trip_ids(data)


async def test_ineligible_quad_group_400(
    client, session, users, org_token
):
    user, _ = users
    await _trip_with_func(session, user.id)
    await session.commit()

    resp = await client.get(
        URL,
        params=_params(tipo_quad_id=TIPO_INELEGIVEL),
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_date_end_before_start_422(client, org_token):
    resp = await client.get(
        URL,
        params=_params(date_start='2025-06-30', date_end='2025-06-01'),
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_excludes_other_org_trip(
    client, session, users, org_token
):
    """Tripulante de outra unidade não aparece (escopo por Tripulante.uae)."""
    _, other = users
    trip = await _trip_with_func(session, other.id, uae='1gt')
    await session.commit()

    resp = await client.get(URL, params=_params(), headers=_auth(org_token))

    assert trip.id not in _all_trip_ids(resp.json()['data'])


async def test_excludes_inactive_trip(
    client, session, users, org_token
):
    user, _ = users
    trip = await _trip_with_func(session, user.id, active=False)
    await session.commit()

    resp = await client.get(URL, params=_params(), headers=_auth(org_token))

    assert trip.id not in _all_trip_ids(resp.json()['data'])


async def test_excludes_func_without_data_op(
    client, session, users, org_token
):
    """Função sem `data_op` (não operacional) é descartada."""
    user, _ = users
    trip = await _trip_with_func(session, user.id, data_op=None)
    await session.commit()

    resp = await client.get(URL, params=_params(), headers=_auth(org_token))

    assert trip.id not in _all_trip_ids(resp.json()['data'])


async def test_excludes_oper_aluno(
    client, session, users, org_token
):
    """Função de aluno (`oper == 'al'`) não é elegível para escala."""
    user, _ = users
    trip = await _trip_with_func(session, user.id, oper='al')
    await session.commit()

    resp = await client.get(URL, params=_params(), headers=_auth(org_token))

    assert trip.id not in _all_trip_ids(resp.json()['data'])


async def test_section_empty_for_func_without_trips(
    client, session, users, org_token
):
    """Pede 'pil' e 'md'; só há piloto → seção 'md' vem vazia."""
    user, _ = users
    await _trip_with_func(session, user.id, func='pil')
    await session.commit()

    resp = await client.get(
        URL,
        params=_params(funcs=['pil', 'md']),
        headers=_auth(org_token),
    )
    data = resp.json()['data']
    secoes = {s['func']: s['trips'] for s in data['sections']}
    assert secoes['md'] == []
    assert len(secoes['pil']) == 1


async def test_missing_active_org_400(client, token):
    resp = await client.get(URL, params=_params(), headers=_auth(token))
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_requires_auth(client):
    resp = await client.get(URL, params=_params())
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
