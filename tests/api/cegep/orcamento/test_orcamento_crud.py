"""
Testes para os endpoints /cegep/orcamento/.

Endpoints:
- GET /cegep/orcamento/ - Orcamento do ano (ou null)
- POST /cegep/orcamento/ - Cria orcamento anual
- PUT /cegep/orcamento/{orc_id} - Atualiza orcamento anual
- GET /cegep/orcamento/{orc_id}/logs - Historico de auditoria

Requer autenticacao. Orcamento e escopado pela org ativa (uae).
"""

from http import HTTPStatus

import pytest

from tests.factories import OrcamentoFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/orcamento/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def orc_payload():
    return {
        'ano_ref': 2026,
        'total': 100000.00,
        'abertura': 50000.00,
        'fechamento': 50000.00,
    }


# ============================================================
# GET /cegep/orcamento/ - Consultar orcamento do ano
# ============================================================


async def test_get_orcamento_vazio(client, token):
    """Sem orcamento cadastrado para o ano, retorna null."""
    resp = await client.get(f'{URL}?ano=2026', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None


async def test_get_orcamento_sem_token(client):
    resp = await client.get(f'{URL}?ano=2026')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# POST /cegep/orcamento/ - Criar orcamento anual
# ============================================================


async def test_post_orcamento_success(client, session, token, orc_payload):
    resp = await client.post(URL, headers=_auth(token), json=orc_payload)

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['ano_ref'] == 2026
    assert data['total'] == 100000.00


async def test_get_orcamento_apos_criar(client, token, orc_payload):
    await client.post(URL, headers=_auth(token), json=orc_payload)

    resp = await client.get(f'{URL}?ano=2026', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data is not None
    assert data['ano_ref'] == 2026


async def test_post_orcamento_soma_invalida(client, token, orc_payload):
    """abertura + fechamento != total -> 422."""
    orc_payload['fechamento'] = 40000.00

    resp = await client.post(URL, headers=_auth(token), json=orc_payload)

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_post_orcamento_duplicado_mesma_org(client, token, orc_payload):
    """Duplicata do mesmo ano, na mesma org, e 400."""
    await client.post(URL, headers=_auth(token), json=orc_payload)

    resp = await client.post(URL, headers=_auth(token), json=orc_payload)

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert 'já existe' in resp.json()['message'].lower()


async def test_post_orcamento_sem_permissao(
    client, token_sem_perm, orc_payload
):
    resp = await client.post(
        URL, headers=_auth(token_sem_perm), json=orc_payload
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


# ============================================================
# PUT /cegep/orcamento/{orc_id} - Atualizar orcamento anual
# ============================================================


@pytest.fixture
async def orc_11gt(session):
    orc = OrcamentoFactory(ano_ref=2026)
    session.add(orc)
    await session.commit()
    await session.refresh(orc)
    return orc


async def test_put_orcamento_success(client, session, token, orc_11gt):
    update_payload = {
        'ano_ref': 2026,
        'total': 120000.00,
        'abertura': 60000.00,
        'fechamento': 60000.00,
    }

    resp = await client.put(
        f'{URL}{orc_11gt.id}', headers=_auth(token), json=update_payload
    )

    assert resp.status_code == HTTPStatus.OK

    await session.refresh(orc_11gt)
    assert float(orc_11gt.total) == 120000.00


async def test_put_orcamento_not_found(client, token, orc_payload):
    resp = await client.put(
        f'{URL}99999', headers=_auth(token), json=orc_payload
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_put_orcamento_sem_permissao(
    client, token_sem_perm, orc_11gt, orc_payload
):
    resp = await client.put(
        f'{URL}{orc_11gt.id}',
        headers=_auth(token_sem_perm),
        json=orc_payload,
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


# ============================================================
# GET /cegep/orcamento/{orc_id}/logs
# ============================================================


async def test_get_orcamento_logs_apos_criar(client, token, orc_payload):
    create_resp = await client.post(
        URL, headers=_auth(token), json=orc_payload
    )
    orc_id = create_resp.json()['data']['id']

    resp = await client.get(f'{URL}{orc_id}/logs', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    logs = resp.json()['data']
    assert len(logs) == 1
    assert logs[0]['action'] == 'create'


async def test_get_orcamento_logs_not_found(client, token):
    resp = await client.get(f'{URL}99999/logs', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND
