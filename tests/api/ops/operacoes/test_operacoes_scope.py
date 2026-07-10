"""Isolamento cross-org de operações (/operacoes).

Toda operação carrega `uae`; os handlers filtram por `active_org` (via
`_get_op`). Um admin da '11gt' não apaga operação da '1gt'.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.operacao import Operacao
from tests.factories import OperacaoFactory

pytestmark = pytest.mark.anyio

URL = '/ops/operacoes/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def op_1gt(session, users):
    _, other = users
    op = OperacaoFactory(created_by=other.id, uae='1gt')
    session.add(op)
    await session.commit()
    await session.refresh(op)
    return op


async def test_delete_cross_org_404(client, session, op_1gt, org_admin_token):
    resp = await client.delete(
        f'{URL}{op_1gt.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND

    # Operação da '1gt' segue no banco.
    still = await session.get(Operacao, op_1gt.id)
    assert still is not None


async def test_lista_nao_traz_op_de_outra_org(client, op_1gt, org_admin_token):
    resp = await client.get(URL, headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    ids = {op['id'] for op in resp.json()['data']['items']}
    assert op_1gt.id not in ids
