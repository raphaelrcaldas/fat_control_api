"""Isolamento cross-org de dados bancários (/cegep/dados-bancarios).

Escopo por `User.unidade == active_org` (join User). Lista, create,
update/delete e órfãos só operam sobre usuários da própria unidade.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios
from fcontrol_api.models.security.resources import UserRole
from tests.factories import DadosBancariosFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/dados-bancarios/'
ORFAOS_URL = '/cegep/dados-bancarios/orfaos'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def _mk_user(session, *, unidade, active=True):
    user = UserFactory(unidade=unidade)
    user.active = active
    session.add(user)
    await session.flush()
    return user


async def _mk_dados(session, user_id):
    dados = DadosBancariosFactory(user_id=user_id)
    session.add(dados)
    await session.flush()
    return dados


async def test_lista_so_traz_usuarios_da_org(client, session, org_admin_token):
    u11 = await _mk_user(session, unidade='11gt')
    u1 = await _mk_user(session, unidade='1gt')
    await _mk_dados(session, u11.id)
    await _mk_dados(session, u1.id)
    await session.commit()

    resp = await client.get(URL, headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    ids = {row['user']['id'] for row in resp.json()['data']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_create_cross_org_404(client, session, org_admin_token):
    u1 = await _mk_user(session, unidade='1gt')
    await session.commit()

    resp = await client.post(
        URL,
        json={
            'user_id': u1.id,
            'banco': 'Banco X',
            'codigo_banco': '001',
            'agencia': '1234-5',
            'conta': '12345-6',
        },
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, session, org_admin_token):
    u1 = await _mk_user(session, unidade='1gt')
    dados = await _mk_dados(session, u1.id)
    await session.commit()

    resp = await client.delete(
        f'{URL}{dados.id}', headers=_auth(org_admin_token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_orfaos_escopado_por_org(client, session, org_admin_token):
    u11 = await _mk_user(session, unidade='11gt', active=False)
    u1 = await _mk_user(session, unidade='1gt', active=False)
    await _mk_dados(session, u11.id)
    await _mk_dados(session, u1.id)
    await session.commit()

    resp = await client.get(ORFAOS_URL, headers=_auth(org_admin_token))
    assert resp.status_code == HTTPStatus.OK
    ids = {item['user_id'] for item in resp.json()['data']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_orfaos_delete_nao_remove_de_outra_org(
    client, session, org_admin_token
):
    u1 = await _mk_user(session, unidade='1gt', active=False)
    dados = await _mk_dados(session, u1.id)
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'ids': [dados.id]},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK
    still = await session.get(DadosBancarios, dados.id)
    assert still is not None
