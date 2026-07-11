"""Isolamento cross-org de CRM (/seg-voo/crm).

CRM pendura num tripulante (escopo `Tripulante.uae`). Um admin da '11gt'
não lê (por user) nem apaga (por trip) CRM de tripulante da '1gt'.
"""

from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.seg_voo.crm import CrmCertificado
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/seg-voo/crm/'
ORFAOS_URL = '/seg-voo/crm/orfaos'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _mk_user_crm(session, *, unidade):
    user = UserFactory(unidade=unidade)
    user.active = False
    session.add(user)
    await session.flush()
    crm = CrmCertificado(
        user_id=user.id,
        data_realizacao=date(2025, 1, 1),
        data_validade=date(2026, 1, 1),
    )
    session.add(crm)
    await session.commit()
    return user, crm


@pytest.fixture
async def trip_crm_1gt(session):
    """Tripulante da '1gt' com um CRM."""
    user = UserFactory(unidade='1gt')
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae='1gt')
    session.add(trip)
    await session.flush()
    crm = CrmCertificado(
        user_id=user.id,
        data_realizacao=date(2025, 1, 1),
        data_validade=date(2026, 1, 1),
    )
    session.add(crm)
    await session.commit()
    return user, trip


async def test_get_by_user_cross_org_retorna_none(client, trip_crm_1gt, token):
    user, _ = trip_crm_1gt
    resp = await client.get(f'{URL}user/{user.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None


async def test_delete_cross_org_404(client, trip_crm_1gt, token):
    _, trip = trip_crm_1gt
    resp = await client.delete(f'{URL}{trip.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND
    # Escopo (tripulante fora da org), não rota inexistente ('Not Found').
    assert resp.json()['message'] == 'Tripulante nao encontrado'


async def test_orfaos_escopado_por_org(client, session, token):
    u11, _ = await _mk_user_crm(session, unidade='11gt')
    u1, _ = await _mk_user_crm(session, unidade='1gt')

    resp = await client.get(ORFAOS_URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    ids = {i['user_id'] for i in resp.json()['data']['itens']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_orfaos_delete_nao_remove_de_outra_org(client, session, token):
    u1, crm = await _mk_user_crm(session, unidade='1gt')

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u1.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['deleted'] == 0
    assert await session.get(CrmCertificado, crm.id) is not None


# ── RBAC (recurso 'crm') ───────────────────────────────────────────


@pytest.fixture
async def user_token_11gt(users, session, make_org_token):
    """Token '11gt' de usuário com role não-admin (sem permissões).

    role_id=2 ('user') não tem grants no seed de teste, então serve para
    validar que o gate barra quem não é admin nem tem a permissão.
    """
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=2, organizacao_id='11gt'))
    await session.commit()
    return other, await make_org_token(other, active_org='11gt')


async def test_list_sem_view_403(client, user_token_11gt):
    """Sem 'crm.view' (e não-admin) a listagem é negada."""
    _, tok = user_token_11gt
    resp = await client.get(URL, headers=_auth(tok))
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_delete_orfaos_sem_delete_403(client, user_token_11gt):
    """Sem 'crm.delete' a limpeza de órfãos é negada."""
    _, tok = user_token_11gt
    resp = await client.request(
        'DELETE', ORFAOS_URL, json={'user_ids': [1]}, headers=_auth(tok)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_upsert_sem_permissao_403(client, session, user_token_11gt):
    """Sem 'crm.create'/'update' o upsert é negado (owner não conta)."""
    other, tok = user_token_11gt
    trip = TripFactory(user_id=other.id, uae='11gt')
    session.add(trip)
    await session.commit()

    resp = await client.put(
        f'{URL}{trip.id}',
        json={
            'data_realizacao': '2025-01-01',
            'data_validade': '2026-01-01',
        },
        headers=_auth(tok),
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_get_by_user_owner_self_service(
    client, session, user_token_11gt
):
    """O próprio militar vê seu CRM sem a permissão (self-service FatBird)."""
    other, tok = user_token_11gt
    trip = TripFactory(user_id=other.id, uae='11gt')
    session.add(trip)
    session.add(
        CrmCertificado(
            user_id=other.id,
            data_realizacao=date(2025, 1, 1),
            data_validade=date(2026, 1, 1),
        )
    )
    await session.commit()

    resp = await client.get(f'{URL}user/{other.id}', headers=_auth(tok))
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['user_id'] == other.id


async def test_get_by_user_terceiro_sem_view_403(
    client, session, user_token_11gt
):
    """Terceiro sem 'crm.view' não lê o CRM de outro militar."""
    _, tok = user_token_11gt
    outro = UserFactory(unidade='11gt')
    session.add(outro)
    await session.commit()

    resp = await client.get(f'{URL}user/{outro.id}', headers=_auth(tok))
    assert resp.status_code == HTTPStatus.FORBIDDEN
