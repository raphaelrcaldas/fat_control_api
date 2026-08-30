"""Tarefas compartilhadas: visibilidade por permissão e escopo de org.

A tarefa é endereçada por PERMISSÃO (`req_resource` + `req_action`), não
por role literal — o destinatário é resolvido na LEITURA. Por isso o
teste da visibilidade não pode usar a fixture `token` (admin, bypass):
ela passaria sem provar que o grant funciona. Daí o `make_perm_token`.

Escopo de org (decisão consciente do desenho): **direta ignora a org
ativa** (é dado da pessoa, e o item exibe a sigla de origem); **tarefa
filtra por `uae == active_org`**.

Nenhum emissor abre tarefa na v1 — elas são semeadas pelo `make_tarefa`.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.enums.notificacao import NotifAudiencia
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import ORG, auth, fatbird_token

pytestmark = pytest.mark.anyio

REQ_RESOURCE = 'users'
REQ_ACTION = 'update'


@pytest.fixture
def make_perm_token(users, session, make_org_token):
    """Token de role NÃO-admin com o grant informado, na org pedida.

    `ensure_role=False` é deliberado: a factory injeta uma role admin
    quando o usuário não tem nenhuma, e admin tem bypass — o teste
    passaria sem exercitar o grant.
    """

    async def _make(resource, action, *, org=ORG, role_name='notif_role'):
        _, other_user = users

        res = await session.scalar(
            select(Resources).where(Resources.name == resource)
        )
        if res is None:
            res = Resources(name=resource, description=resource)
            session.add(res)
            await session.flush()

        perm = await session.scalar(
            select(Permissions).where(
                Permissions.resource_id == res.id,
                Permissions.name == action,
            )
        )
        if perm is None:
            perm = Permissions(
                resource_id=res.id, name=action, description=action
            )
            session.add(perm)
            await session.flush()

        role = Roles(name=role_name, description=role_name)
        session.add(role)
        await session.flush()
        session.add(RolePermissions(role_id=role.id, permission_id=perm.id))
        session.add(
            UserRole(
                user_id=other_user.id, role_id=role.id, organizacao_id=org
            )
        )
        await session.commit()

        return await make_org_token(
            other_user, active_org=org, ensure_role=False
        )

    return _make


@pytest.fixture
async def token_admin_1gt(users, session, make_org_token):
    """Admin da '1gt' — a lente de OUTRA unidade sobre a mesma tabela."""
    _, other_user = users
    session.add(
        UserRole(user_id=other_user.id, role_id=1, organizacao_id='1gt')
    )
    await session.commit()

    return await make_org_token(
        other_user, active_org='1gt', ensure_role=False
    )


@pytest.fixture
async def tarefa(make_tarefa):
    """Uma tarefa aberta na '11gt', exigindo `users.update`."""
    return await make_tarefa(
        req_resource=REQ_RESOURCE, req_action=REQ_ACTION, chave_dedupe='u:7'
    )


# ── Visibilidade ────────────────────────────────────────────────────


async def test_admin_da_org_ve_a_tarefa(client, token, tarefa):
    """Admin não tem linha em `role_permissions` — passa pelo bypass."""
    lista = await client.get('/notificacoes/', headers=auth(token))
    contador = await client.get('/notificacoes/contador', headers=auth(token))

    assert tarefa.id in {n['id'] for n in lista.json()['data']}
    assert contador.json()['data']['tarefas'] == 1


async def test_nao_admin_com_a_permissao_ve_a_tarefa(
    client, tarefa, make_perm_token
):
    """O grant `users.update` basta — é assim que a tarefa é endereçada."""
    token_perm = await make_perm_token(REQ_RESOURCE, REQ_ACTION)

    lista = await client.get('/notificacoes/', headers=auth(token_perm))

    assert tarefa.id in {n['id'] for n in lista.json()['data']}


async def test_nao_admin_com_outra_permissao_nao_ve(
    client, tarefa, make_perm_token
):
    """Permissão diferente não abre a tarefa (o par resource+action casa)."""
    token_perm = await make_perm_token('ops.quadrinhos', 'create')

    lista = await client.get('/notificacoes/', headers=auth(token_perm))

    assert tarefa.id not in {n['id'] for n in lista.json()['data']}


async def test_sem_permissao_nenhuma_nao_ve_a_tarefa(
    client, tarefa, token_sem_perm
):
    """Sem nenhum grant na org ativa só restam as diretas."""
    lista = await client.get('/notificacoes/', headers=auth(token_sem_perm))
    contador = await client.get(
        '/notificacoes/contador', headers=auth(token_sem_perm)
    )

    assert lista.json()['total'] == 0
    assert contador.json()['data']['tarefas'] == 0


async def test_admin_de_outra_org_nao_ve_a_tarefa(
    client, tarefa, token_admin_1gt
):
    """Tarefa é escopada por `uae`: a lente da '1gt' não alcança a '11gt'."""
    lista = await client.get('/notificacoes/', headers=auth(token_admin_1gt))

    assert tarefa.id not in {n['id'] for n in lista.json()['data']}


async def test_fatbird_nunca_ve_tarefa(
    client, users, trips, tarefa, make_direta
):
    """Tripulante não tem role — tarefa nunca entra na caixa dele."""
    user, _ = users
    minha = await make_direta(user, audiencia=NotifAudiencia.TRIPULANTE.value)

    lista = await client.get(
        '/notificacoes/', headers=auth(fatbird_token(user))
    )
    contador = await client.get(
        '/notificacoes/contador', headers=auth(fatbird_token(user))
    )

    assert {n['id'] for n in lista.json()['data']} == {minha.id}
    assert contador.json()['data']['tarefas'] == 0


# ── Direta atravessa a org ativa (decisão do desenho) ───────────────


async def test_direta_de_outra_org_aparece(client, users, token, make_direta):
    """A direta é dado da PESSOA: a org ativa não a esconde.

    Congela a decisão do §2 do plano — o item exibe a sigla de origem, e
    filtrar por org ativa faria a pessoa perder o próprio aviso ao trocar
    de unidade no switcher.
    """
    user, _ = users
    de_outra_org = await make_direta(user, uae='1gt', titulo='Da 1gt')

    lista = await client.get('/notificacoes/', headers=auth(token))

    item = next(n for n in lista.json()['data'] if n['id'] == de_outra_org.id)
    assert item['uae'] == '1gt'


# ── /resolver ───────────────────────────────────────────────────────


async def test_resolver_com_a_permissao(
    client, session, users, tarefa, make_perm_token
):
    """Quem tem o grant dá o desfecho — e a auditoria vai no mesmo commit."""
    _, other_user = users
    token_perm = await make_perm_token(REQ_RESOURCE, REQ_ACTION)

    response = await client.post(
        f'/notificacoes/{tarefa.id}/resolver', headers=auth(token_perm)
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['resolved_at'] is not None
    assert data['resolved_by'] == other_user.id

    log = await session.scalar(
        select(UserActionLog).where(
            UserActionLog.resource == 'notificacoes',
            UserActionLog.resource_id == tarefa.id,
            UserActionLog.action == 'resolve',
        )
    )
    assert log is not None
    assert log.user_id == other_user.id


async def test_resolver_idempotente(client, session, tarefa, make_perm_token):
    """A segunda chamada não sobrescreve quem resolveu primeiro."""
    token_perm = await make_perm_token(REQ_RESOURCE, REQ_ACTION)

    primeira = await client.post(
        f'/notificacoes/{tarefa.id}/resolver', headers=auth(token_perm)
    )
    segunda = await client.post(
        f'/notificacoes/{tarefa.id}/resolver', headers=auth(token_perm)
    )

    assert segunda.status_code == HTTPStatus.OK
    assert (
        segunda.json()['data']['resolved_at']
        == primeira.json()['data']['resolved_at']
    )

    logs = await session.scalars(
        select(UserActionLog).where(
            UserActionLog.resource == 'notificacoes',
            UserActionLog.resource_id == tarefa.id,
        )
    )
    assert len(list(logs.all())) == 1


async def test_tarefa_resolvida_sai_do_contador(
    client, token, tarefa, make_perm_token
):
    token_perm = await make_perm_token(REQ_RESOURCE, REQ_ACTION)
    await client.post(
        f'/notificacoes/{tarefa.id}/resolver', headers=auth(token_perm)
    )

    contador = await client.get('/notificacoes/contador', headers=auth(token))

    assert contador.json()['data']['tarefas'] == 0


async def test_resolver_sem_permissao_403(
    client, session, tarefa, token_sem_perm
):
    """A tarefa existe para a org ativa, mas o gate dinâmico nega."""
    response = await client.post(
        f'/notificacoes/{tarefa.id}/resolver', headers=auth(token_sem_perm)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN

    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == tarefa.id)
    )
    assert db_notif.resolved_at is None


async def test_resolver_de_outra_org_404(client, tarefa, token_admin_1gt):
    """Fora da org ativa a tarefa nem existe — 404 antes do gate."""
    response = await client.post(
        f'/notificacoes/{tarefa.id}/resolver', headers=auth(token_admin_1gt)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_resolver_direta_404(client, users, token, make_direta):
    """`/resolver` é só para tarefa; direta se marca como lida."""
    user, _ = users
    direta = await make_direta(user)

    response = await client.post(
        f'/notificacoes/{direta.id}/resolver', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_fatbird_nao_resolve_tarefa(client, users, trips, tarefa):
    """Audiência do token é tripulante: a tarefa não existe para ele."""
    user, _ = users

    response = await client.post(
        f'/notificacoes/{tarefa.id}/resolver',
        headers=auth(fatbird_token(user)),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
