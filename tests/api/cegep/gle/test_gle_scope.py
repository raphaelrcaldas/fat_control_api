"""Isolamento cross-org das missoes de GLE (/cegep/gle/missoes).

Toda missao carrega `uae` e os handlers filtram por
`MissaoGle.uae == active_org`. A recusa e **404, nao 403**: a existencia da
missao de outra unidade nao e informacao a dar.

O militar tambem e escopado: o gate autoriza a **acao**, nao o **alvo** —
sem `User.unidade == active_org` um id de fora entraria na missao e o GET
seguinte devolveria nome e SARAM daquele militar.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole

pytestmark = pytest.mark.anyio

URL = '/cegep/gle/missoes'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _payload(loc_id, user_id):
    return {
        'descricao': 'OS 168-BAGL-26042026',
        'trechos': [
            {
                'loc_esp_id': loc_id,
                'chegada': '2026-04-26T14:15:00',
                'afastamento': '2026-05-29T02:35:00',
            }
        ],
        'militares_ids': [user_id],
    }


@pytest.fixture
async def token_1gt(session, users, make_org_token):
    """Token de admin escopado na '1gt', fora da lente do token padrao."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


@pytest.fixture
async def missao_11gt(client, token, users, loc_a):
    """Missao criada na '11gt' (a org do token padrao)."""
    user, _ = users
    resp = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )
    return resp.json()['data']


# --- Isolamento entre organizacoes ---


async def test_lista_nao_traz_missao_de_outra_org(
    client, missao_11gt, token_1gt
):
    resp = await client.get(URL, headers=_auth(token_1gt))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] == []


async def test_get_cross_org_404(client, missao_11gt, token_1gt):
    resp = await client.get(
        f'{URL}/{missao_11gt["id"]}', headers=_auth(token_1gt)
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_put_cross_org_404(client, missao_11gt, token_1gt, users, loc_a):
    user, _ = users

    resp = await client.put(
        f'{URL}/{missao_11gt["id"]}',
        headers=_auth(token_1gt),
        json=_payload(loc_a.id, user.id),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, missao_11gt, token_1gt):
    resp = await client.delete(
        f'{URL}/{missao_11gt["id"]}', headers=_auth(token_1gt)
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_controle_positivo_a_propria_org_enxerga(
    client, token, missao_11gt
):
    """Sem este controle, os 404 acima passariam ate com a rota quebrada."""
    resp = await client.get(f'{URL}/{missao_11gt["id"]}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == missao_11gt['id']


# --- O alvo tambem e escopado, nao so a acao ---


async def test_nao_aceita_militar_de_outra_unidade(
    client, token, session, users, loc_a
):
    """Militar de fora da org ativa e recusado com 422 neutro."""
    _, outro = users
    outro.unidade = '1gt'
    await session.commit()

    resp = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, outro.id)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_put_tambem_recusa_militar_de_outra_unidade(
    client, token, session, users, loc_a, missao_11gt
):
    _, outro = users
    outro.unidade = '1gt'
    await session.commit()

    resp = await client.put(
        f'{URL}/{missao_11gt["id"]}',
        headers=_auth(token),
        json=_payload(loc_a.id, outro.id),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# --- RBAC ---


async def test_sem_permissao_403(client, token_sem_perm):
    resp = await client.get(URL, headers=_auth(token_sem_perm))

    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_sem_token_401(client):
    resp = await client.get(URL)

    assert resp.status_code == HTTPStatus.UNAUTHORIZED
