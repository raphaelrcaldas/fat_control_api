"""
Testes para o endpoint PUT /users/{user_id}.

Este endpoint permite atualizar dados de um usuário.
Requer permissão 'user:update'.
"""

from datetime import date
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.shared.users import User

pytestmark = pytest.mark.anyio


async def test_update_user_success(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que um usuário com permissão pode atualizar outro usuário.
    """
    token = await make_org_token(user_with_update_permission)
    _, other_user = users

    update_data = {'nome_guerra': 'atualizado'}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == 'Usuario atualizado com sucesso'
    assert resp['data'] is not None

    # Verifica que os dados foram atualizados no banco
    await session.refresh(other_user)
    db_user = await session.scalar(
        select(User).where(User.id == other_user.id)
    )

    assert db_user.nome_guerra == update_data['nome_guerra']


async def test_update_user_partial_update(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que é possível fazer atualização parcial (apenas alguns campos).
    """
    token = await make_org_token(user_with_update_permission)
    _, other_user = users

    original_nome_guerra = other_user.nome_guerra

    # Atualiza apenas o telefone
    update_data = {'telefone': '21999998888'}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(other_user)

    # Verifica que apenas o campo atualizado mudou
    assert other_user.telefone == update_data['telefone']
    assert other_user.nome_guerra == original_nome_guerra


async def test_update_user_nao_move_de_unidade(
    client, session, users, user_with_update_permission, make_org_token
):
    """A unidade não é editável pelo PUT — `UserUpdate` sequer a aceita.

    O usuário pertence à organização em que foi cadastrado; "mover" alguém de
    unidade não é operação do PUT. Mandar `unidade` no corpo é simplesmente
    ignorado, e o guard é este teste: se alguém devolver o campo ao schema, o
    registro passaria a trocar de organização por um PATCH silencioso.
    """
    token = await make_org_token(user_with_update_permission)
    _, other_user = users

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'nome_guerra': 'atualizado', 'unidade': '1gt'},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(other_user)
    assert other_user.nome_guerra == 'atualizado'
    assert other_user.unidade == '11gt'


async def test_update_user_without_permission_fails(
    client, users, make_org_token
):
    """
    Testa que usuário sem permissão não pode atualizar usuários.
    """
    user, other_user = users
    # ensure_role=False: o teste valida a ausência de permissão, então NÃO
    # pode receber a role default (admin), que tem bypass no gate.
    token = await make_org_token(user, ensure_role=False)

    update_data = {'nome_guerra': 'atualizado'}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_update_user_not_found(
    client, user_with_update_permission, make_org_token
):
    """
    Testa que atualizar usuário inexistente retorna 404.
    """
    token = await make_org_token(user_with_update_permission)

    update_data = {'nome_guerra': 'atualizado'}

    response = await client.put(
        '/users/99999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'nao encontrado' in resp['message'].lower()


async def test_update_user_duplicate_saram_fails(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que não é possível atualizar para um saram já existente.
    """
    token = await make_org_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o saram de user
    update_data = {'saram': user.saram}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'saram' in resp['message'].lower()


async def test_update_user_duplicate_cpf_fails(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que não é possível atualizar para um CPF já existente.
    """
    token = await make_org_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o CPF de user
    update_data = {'cpf': user.cpf}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'cpf' in resp['message'].lower()


async def test_update_user_duplicate_id_fab_fails(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que não é possível atualizar para um ID FAB já existente.
    """
    token = await make_org_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o CPF de user
    update_data = {'id_fab': user.id_fab}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'id fab' in resp['message'].lower()


async def test_update_user_duplicate_zimbra_fails(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que não é possível atualizar para um Zimbra já existente.
    """
    token = await make_org_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o Zimbra de user
    update_data = {'email_fab': user.email_fab}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'zimbra' in resp['message'].lower()


async def test_update_user_duplicate_email_pessoal_fails(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que não é possível atualizar para um email pessoal já existente.
    """
    token = await make_org_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o Email pessoal de user
    update_data = {'email_pess': user.email_pess}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'email pessoal' in resp['message'].lower()


async def test_update_user_without_token_fails(client, users):
    """
    Testa que requisição sem token é rejeitada.
    """
    _, other_user = users

    update_data = {'nome_guerra': 'atualizado'}

    response = await client.put(
        f'/users/{other_user.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_user_can_update_same_user_unique_fields(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que é possível atualizar outros campos mantendo o mesmo saram/cpf.

    Importante para verificar que a validação de unicidade
    exclui o próprio usuário.
    """
    token = await make_org_token(user_with_update_permission)
    _, other_user = users

    # Reenvia o próprio saram (não pode colidir consigo mesmo) e muda outro
    # campo, para provar que o update de fato ocorreu.
    update_data = {
        'saram': other_user.saram,  # Mantém o mesmo
        'nome_guerra': 'atualizado',  # Muda outro campo
    }

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(other_user)
    assert other_user.nome_guerra == 'atualizado'


async def test_update_user_with_date_field(
    client, session, users, user_with_update_permission, make_org_token
):
    """
    Testa que é possível atualizar campos do tipo date.

    Este teste garante que a cobertura inclui o código que
    converte datas para isoformat() no log de auditoria.
    """
    token = await make_org_token(user_with_update_permission)
    _, other_user = users

    # Atualiza um campo de data
    new_birth_date = date(1990, 5, 15)
    update_data = {'nasc': new_birth_date.isoformat()}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == 'Usuario atualizado com sucesso'

    # Verifica que a data foi atualizada no banco
    await session.refresh(other_user)
    db_user = await session.scalar(
        select(User).where(User.id == other_user.id)
    )

    assert db_user.nasc == new_birth_date
