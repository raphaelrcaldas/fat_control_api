"""Isolamento cross-org de comissionamentos (/cegep/comiss).

Todo comissionamento carrega `uae`; os handlers filtram por
`Comissionamento.uae == active_org`. Um admin da '11gt' não enxerga, nem
lê/apaga, comissionamento da '1gt'.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole
from tests.factories import ComissFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/comiss/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def comiss_1gt(session, users):
    """Comissionamento na org '1gt' (fora da lente da '11gt')."""
    _, other = users
    comiss = ComissFactory(user_id=other.id, uae='1gt')
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)
    return comiss


async def test_lista_nao_traz_comiss_de_outra_org(client, comiss_1gt, token):
    resp = await client.get(URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    ids = {c['id'] for c in resp.json()['data']}
    assert comiss_1gt.id not in ids


async def test_get_by_id_cross_org_404(client, comiss_1gt, token):
    resp = await client.get(f'{URL}{comiss_1gt.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, comiss_1gt, token):
    resp = await client.delete(
        f'{URL}{comiss_1gt.id}?confirm=true', headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_org_1gt_enxerga_o_proprio_comiss(
    client, session, users, comiss_1gt, make_org_token
):
    """Sanidade: o admin da '1gt' vê o comiss que a '11gt' não vê."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    token_1gt = await make_org_token(other, active_org='1gt')

    resp = await client.get(URL, headers=_auth(token_1gt))
    assert resp.status_code == HTTPStatus.OK
    ids = {c['id'] for c in resp.json()['data']}
    assert comiss_1gt.id in ids
