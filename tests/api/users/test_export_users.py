"""POST /users/export — hidratação de PII sob `users.export`.

O endpoint entrega CPF, e-mails e datas que a listagem não carrega, então o
que importa aqui é quem recebe e de qual unidade: sem a permissão, 403; id de
outra organização é descartado em silêncio (não 404) e o descarte fica na
auditoria.
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.schemas.users import EXPORT_MAX_IDS
from tests.api.users.conftest import _grant_user_permission
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio

URL = '/users/export'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def militar_1gt(session):
    militar = UserFactory(unidade='1gt')
    session.add(militar)
    await session.commit()
    await session.refresh(militar)
    return militar


async def test_export_sem_token_401(client):
    resp = await client.post(URL, json={'ids': [1]})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


async def test_export_sem_permissao_403(client, users, token_sem_perm):
    _, other = users
    resp = await client.post(
        URL, json={'ids': [other.id]}, headers=_auth(token_sem_perm)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    ('acao', 'status'),
    [('view', HTTPStatus.FORBIDDEN), ('export', HTTPStatus.OK)],
)
async def test_export_exige_users_export_e_nao_view(
    client, session, users, make_org_token, acao, status
):
    """O gate é `users.export`: quem só lista usuários não tira PII.

    Role não-admin na '11gt' — o `token` padrão é admin e passaria pelo
    bypass sem exercitar a permissão.
    """
    user, other = users
    await _grant_user_permission(session, user, acao)
    token = await make_org_token(user)

    resp = await client.post(
        URL, json={'ids': [other.id]}, headers=_auth(token)
    )
    assert resp.status_code == status


async def test_export_descarta_militar_de_outra_org(
    client, session, users, militar_1gt, token
):
    user, other = users
    ids = [other.id, militar_1gt.id, user.id, other.id]

    resp = await client.post(URL, json={'ids': ids}, headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    # Ordem do carrinho, sem repetição e sem o militar da '1gt'.
    assert [d['id'] for d in data] == [other.id, user.id]
    # A PII que justifica o gate próprio vem na resposta.
    assert {'cpf', 'email_pess', 'nasc'} <= data[0].keys()

    log = await session.scalar(
        select(UserActionLog).where(
            UserActionLog.action == 'export',
            UserActionLog.resource == 'users',
        )
    )
    assert log.user_id == user.id
    assert json.loads(log.after) == {
        'solicitados': 3,
        'retornados': 2,
        'org': '11gt',
    }


async def test_export_admin_de_sistema_alcanca_todas_as_orgs(
    client, users, militar_1gt, token_sistema
):
    user, _ = users
    resp = await client.post(
        URL,
        json={'ids': [user.id, militar_1gt.id]},
        headers=_auth(token_sistema),
    )

    assert resp.status_code == HTTPStatus.OK
    assert [d['id'] for d in resp.json()['data']] == [
        user.id,
        militar_1gt.id,
    ]


async def test_export_acima_do_teto_422(client, token):
    ids = list(range(1, EXPORT_MAX_IDS + 2))
    resp = await client.post(URL, json={'ids': ids}, headers=_auth(token))
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
