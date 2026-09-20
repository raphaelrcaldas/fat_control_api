"""Auditoria (UserActionLog) dos vínculos user↔role (`/security/roles/users`).

O histórico da página do usuário (`UserAudit` no client) lê os logs por
`resource='users'` + `resource_id=<id do usuário>`. Por isso a alteração de
perfil é gravada **no alvo** — `resource_id` é o usuário que teve a role
mexida, e `user_id` é quem mexeu —, e não no id do vínculo: gravar em
`resource='roles'` deixaria o evento invisível nessa trilha.

`organizacao` entra no before/after porque um usuário pode ter vínculo em
mais de uma org; sem ela, "perfil alterado" é ambíguo na trilha.

Seeds de role: 1=admin, 2=user, 3=viewer. Tenants: '11gt' e '1gt'.
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.security.resources import UserRole

pytestmark = pytest.mark.anyio

RESOURCE = 'users'


async def _bind(session, user_id, role_id, org):
    session.add(UserRole(user_id=user_id, role_id=role_id, organizacao_id=org))
    await session.commit()


async def _logs(session, resource_id, action=None):
    stmt = select(UserActionLog).where(
        UserActionLog.resource == RESOURCE,
        UserActionLog.resource_id == resource_id,
    )
    if action:
        stmt = stmt.where(UserActionLog.action == action)

    result = await session.scalars(stmt.order_by(UserActionLog.id))
    return list(result.all())


def _payload(raw):
    return json.loads(raw) if raw else None


# --- add_user_role -------------------------------------------------------- #


async def test_add_user_role_grava_log_no_alvo(
    client, session, users, unit_admin_token
):
    user, other = users

    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, other.id, 'role-add')
    assert len(logs) == 1
    log = logs[0]
    # Quem alterou é o admin; o alvo é o dono da trilha.
    assert log.user_id == user.id
    assert _payload(log.before) is None
    assert _payload(log.after) == {'role': 'user', 'organizacao': '11gt'}


async def test_add_user_role_nao_loga_no_autor(
    client, session, users, unit_admin_token
):
    """O evento pertence ao alvo — não pode aparecer na trilha do admin."""
    user, other = users

    await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )

    assert await _logs(session, user.id) == []


async def test_add_user_role_sistema_loga_organizacao_sistema(
    client, session, users, sysadmin_token
):
    """Vínculo de sistema (org NULL) não pode logar organização vazia."""
    _, other = users

    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 1, 'organizacao_id': None},
        headers={'Authorization': f'Bearer {sysadmin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, other.id, 'role-add')
    assert len(logs) == 1
    assert _payload(logs[0].after) == {
        'role': 'admin',
        'organizacao': 'Sistema',
    }


async def test_add_user_role_recusado_nao_loga(
    client, session, users, unit_admin_token
):
    """Vínculo duplicado (409) não deixa rastro na trilha."""
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')

    response = await client.post(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.CONFLICT

    assert await _logs(session, other.id) == []


# --- update_user_role ----------------------------------------------------- #


async def test_update_user_role_grava_de_para(
    client, session, users, unit_admin_token
):
    user, other = users
    await _bind(session, other.id, role_id=2, org='11gt')

    response = await client.put(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, other.id, 'role-update')
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == user.id
    assert _payload(log.before) == {'role': 'user', 'organizacao': '11gt'}
    assert _payload(log.after) == {'role': 'viewer', 'organizacao': '11gt'}


async def test_update_user_role_sem_mudanca_nao_loga(
    client, session, users, unit_admin_token
):
    """Reenviar a mesma role é no-op: evento sem mudança só polui a trilha."""
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')

    response = await client.put(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    assert await _logs(session, other.id) == []


async def test_update_user_role_recusado_nao_loga(
    client, session, users, unit_admin_token
):
    """Vínculo inexistente (404) não deixa rastro na trilha."""
    _, other = users

    response = await client.put(
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND

    assert await _logs(session, other.id) == []


# --- delete_user_role ----------------------------------------------------- #


async def test_delete_user_role_grava_o_que_foi_removido(
    client, session, users, unit_admin_token
):
    """O `after` vem preenchido com a role vazia.

    `Historico` monta as linhas de diff a partir das chaves de `after`:
    com `after=None` a entrada apareceria sem dizer qual perfil saiu.
    """
    user, other = users
    await _bind(session, other.id, role_id=2, org='11gt')

    response = await client.request(
        'DELETE',
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 2, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, other.id, 'role-delete')
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == user.id
    assert _payload(log.before) == {'role': 'user', 'organizacao': '11gt'}
    assert _payload(log.after) == {'role': '', 'organizacao': '11gt'}


async def test_delete_user_role_recusado_nao_loga(
    client, session, users, unit_admin_token
):
    """Roles que não conferem (400) não deixam rastro na trilha."""
    _, other = users
    await _bind(session, other.id, role_id=2, org='11gt')

    response = await client.request(
        'DELETE',
        '/security/roles/users/',
        json={'user_id': other.id, 'role_id': 3, 'organizacao_id': '11gt'},
        headers={'Authorization': f'Bearer {unit_admin_token}'},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST

    assert await _logs(session, other.id) == []


# --- trilha completa ------------------------------------------------------ #


async def test_trilha_do_usuario_acumula_os_tres_eventos(
    client, session, users, unit_admin_token
):
    """Concessão, alteração e remoção aparecem em ordem na mesma trilha."""
    _, other = users
    headers = {'Authorization': f'Bearer {unit_admin_token}'}
    vinculo = {'user_id': other.id, 'organizacao_id': '11gt'}

    await client.post(
        '/security/roles/users/',
        json={**vinculo, 'role_id': 2},
        headers=headers,
    )
    await client.put(
        '/security/roles/users/',
        json={**vinculo, 'role_id': 3},
        headers=headers,
    )
    await client.request(
        'DELETE',
        '/security/roles/users/',
        json={**vinculo, 'role_id': 3},
        headers=headers,
    )

    acoes = [log.action for log in await _logs(session, other.id)]
    assert acoes == ['role-add', 'role-update', 'role-delete']
