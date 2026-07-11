"""Isolamento cross-org dos cartões de instrução (/instrucao/cartoes).

Cartão de instrução pendura num tripulante (escopo `Tripulante.uae`). Um
admin da '11gt' não apaga cartão de tripulante da '1gt' (404 na resolução
do tripulante fora da org).
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.instrucao.cartoes import Cartao
from fcontrol_api.models.security.resources import UserRole
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/instrucao/cartoes/'
ORFAOS_URL = '/instrucao/cartoes/orfaos'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def trip_1gt(session):
    user = UserFactory(unidade='1gt')
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae='1gt')
    session.add(trip)
    await session.commit()
    return trip


async def _mk_user_cartao(session, *, unidade):
    user = UserFactory(unidade=unidade)
    user.active = False
    session.add(user)
    await session.flush()
    cartao = Cartao(
        user_id=user.id,
        ptai_validade=None,
        tai_s_validade=None,
        tai_s1_validade=None,
        cvi_validade=None,
        hab_espanhol=None,
        val_espanhol=None,
        hab_ingles=None,
        val_ingles=None,
    )
    session.add(cartao)
    await session.commit()
    return user, cartao


async def test_delete_cross_org_404(client, trip_1gt, token):
    resp = await client.delete(f'{URL}{trip_1gt.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND
    # Escopo (tripulante fora da org), não rota inexistente ('Not Found').
    assert resp.json()['message'] == 'Tripulante nao encontrado'


async def test_orfaos_escopado_por_org(client, session, token):
    u11, _ = await _mk_user_cartao(session, unidade='11gt')
    u1, _ = await _mk_user_cartao(session, unidade='1gt')

    resp = await client.get(ORFAOS_URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    ids = {i['user_id'] for i in resp.json()['data']['itens']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_orfaos_delete_nao_remove_de_outra_org(client, session, token):
    u1, cartao = await _mk_user_cartao(session, unidade='1gt')

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u1.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['deleted'] == 0
    assert await session.get(Cartao, cartao.id) is not None


# ── RBAC (recurso 'instrucao-cartoes') ─────────────────────────────


@pytest.fixture
async def user_token_11gt(users, session, make_org_token):
    """Token '11gt' de usuário com role não-admin (sem permissões)."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=2, organizacao_id='11gt'))
    await session.commit()
    return other, await make_org_token(other, active_org='11gt')


async def test_list_sem_view_403(client, user_token_11gt):
    """Sem 'instrucao-cartoes.view' (e não-admin) a listagem é negada."""
    _, tok = user_token_11gt
    resp = await client.get(URL, headers=_auth(tok))
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_orfaos_sem_view_403(client, user_token_11gt):
    """Sem 'instrucao-cartoes.view' o resumo de órfãos é negado."""
    _, tok = user_token_11gt
    resp = await client.get(ORFAOS_URL, headers=_auth(tok))
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_delete_orfaos_sem_delete_403(client, user_token_11gt):
    """Sem 'instrucao-cartoes.delete' a limpeza de órfãos é negada."""
    _, tok = user_token_11gt
    resp = await client.request(
        'DELETE', ORFAOS_URL, json={'user_ids': [1]}, headers=_auth(tok)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_upsert_sem_permissao_403(client, session, user_token_11gt):
    """Sem 'instrucao-cartoes.create'/'update' o upsert é negado."""
    other, tok = user_token_11gt
    trip = TripFactory(user_id=other.id, uae='11gt', func='pil')
    session.add(trip)
    await session.commit()

    resp = await client.put(
        f'{URL}{trip.id}',
        json={'cvi_validade': '2026-01-01'},
        headers=_auth(tok),
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN
