"""Isolamento cross-org do orcamento anual (/cegep/orcamento).

Todo orcamento carrega `uae`; os handlers filtram por
`OrcamentoAnual.uae == active_org`. Um admin da '11gt' nao enxerga, nem
le/atualiza, orcamento da '1gt' — e o mesmo ano pode ter um orcamento
distinto em cada org.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole
from tests.factories import ComissFactory, OrcamentoFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/orcamento/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def orc_11gt(session):
    """Orcamento de 2026 na org '11gt' (a lente do token padrao)."""
    orc = OrcamentoFactory(ano_ref=2026, uae='11gt')
    session.add(orc)
    await session.commit()
    await session.refresh(orc)
    return orc


@pytest.fixture
async def token_1gt(session, users, make_org_token):
    """Token de admin escopado na org '1gt' (fora da lente do orc_11gt)."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def test_get_nao_traz_orcamento_de_outra_org(
    client, orc_11gt, token_1gt
):
    resp = await client.get(f'{URL}?ano=2026', headers=_auth(token_1gt))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None


async def test_put_cross_org_404(client, orc_11gt, token_1gt):
    payload = {
        'ano_ref': 2026,
        'total': 100000.00,
        'abertura': 50000.00,
        'fechamento': 50000.00,
    }

    resp = await client.put(
        f'{URL}{orc_11gt.id}', headers=_auth(token_1gt), json=payload
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_logs_cross_org_404(client, orc_11gt, token_1gt):
    resp = await client.get(
        f'{URL}{orc_11gt.id}/logs', headers=_auth(token_1gt)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_post_mesmo_ano_outra_org_permitido(client, orc_11gt, token_1gt):
    """Orgs distintas podem ter orcamento do mesmo ano_ref."""
    payload = {
        'ano_ref': 2026,
        'total': 80000.00,
        'abertura': 40000.00,
        'fechamento': 40000.00,
    }

    resp = await client.post(URL, headers=_auth(token_1gt), json=payload)

    assert resp.status_code == HTTPStatus.CREATED


async def test_org_1gt_enxerga_o_proprio_orcamento(
    client, session, users, make_org_token
):
    """Sanidade: o admin da '1gt' ve o orcamento que a '11gt' nao ve."""
    _, other = users
    orc_1gt = OrcamentoFactory(ano_ref=2026, uae='1gt')
    session.add(orc_1gt)
    await session.commit()
    await session.refresh(orc_1gt)

    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    token_1gt = await make_org_token(other, active_org='1gt')

    resp = await client.get(f'{URL}?ano=2026', headers=_auth(token_1gt))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == orc_1gt.id


async def test_summary_comiss_nao_vaza_orcamento_de_outra_org(
    client, session, users, token
):
    """Summary de /cegep/comiss usa o orcamento da org ativa apenas.

    Um orcamento de 2026 cadastrado na '1gt' nao deve aparecer no summary
    consultado com a org ativa '11gt' (token padrao) — orc_total fica 0.
    """
    user, _ = users
    comiss = ComissFactory(user_id=user.id, uae='11gt')
    orc_1gt = OrcamentoFactory(ano_ref=2026, uae='1gt')
    session.add_all([comiss, orc_1gt])
    await session.commit()

    resp = await client.get(
        '/cegep/comiss/summary?ano=2026', headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['orcamento_id'] is None
    assert data['total']['orcamento'] == 0.0
