"""Isolamento cross-org de ordens de missão (/ops/om).

Toda OM carrega `uae`; os handlers filtram `OrdemMissao.uae == active_org`.
Um admin da '11gt' não lê nem apaga OM da '1gt' — e o teste inclui um
controle positivo (admin da '1gt' enxerga a própria OM) para garantir que
o 404 vem do escopo de org, não de rota inexistente.

(A fixture autouse `seed_aeronaves` do conftest do módulo cobre a FK de
`matricula_anv`.)
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole
from tests.factories import OrdemMissaoFactory

pytestmark = pytest.mark.anyio

URL = '/ops/om/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


@pytest.fixture
async def om_1gt(session, users):
    _, other = users
    om = OrdemMissaoFactory(created_by=other.id, uae='1gt')
    session.add(om)
    await session.commit()
    await session.refresh(om)
    return om


async def test_get_by_id_cross_org_404(client, om_1gt, org_admin_token):
    resp = await client.get(
        f'{URL}{om_1gt.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, om_1gt, org_admin_token):
    resp = await client.delete(
        f'{URL}{om_1gt.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
    # Prova que caiu no handler (escopo), não em rota inexistente.
    assert resp.json()['message'] == 'Ordem de missão não encontrada'


async def test_org_dona_enxerga_a_propria_om(client, om_1gt, admin_1gt_token):
    """Controle positivo: admin da '1gt' vê a OM que a '11gt' não vê."""
    resp = await client.get(
        f'{URL}{om_1gt.id}', headers=_auth(admin_1gt_token)
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == om_1gt.id
