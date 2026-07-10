"""Isolamento cross-org de CRM (/seg-voo/crm).

CRM pendura num tripulante (escopo `Tripulante.uae`). Um admin da '11gt'
não lê (por user) nem apaga (por trip) CRM de tripulante da '1gt'.
"""

from datetime import date
from http import HTTPStatus

import pytest

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


async def test_get_by_user_cross_org_retorna_none(
    client, trip_crm_1gt, org_admin_token
):
    user, _ = trip_crm_1gt
    resp = await client.get(
        f'{URL}user/{user.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None


async def test_delete_cross_org_404(client, trip_crm_1gt, org_admin_token):
    _, trip = trip_crm_1gt
    resp = await client.delete(
        f'{URL}{trip.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
    # Escopo (tripulante fora da org), não rota inexistente ('Not Found').
    assert resp.json()['message'] == 'Tripulante nao encontrado'


async def test_orfaos_escopado_por_org(client, session, org_admin_token):
    u11, _ = await _mk_user_crm(session, unidade='11gt')
    u1, _ = await _mk_user_crm(session, unidade='1gt')

    resp = await client.get(ORFAOS_URL, headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    ids = {i['user_id'] for i in resp.json()['data']['itens']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_orfaos_delete_nao_remove_de_outra_org(
    client, session, org_admin_token
):
    u1, crm = await _mk_user_crm(session, unidade='1gt')

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u1.id]},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['deleted'] == 0
    assert await session.get(CrmCertificado, crm.id) is not None
