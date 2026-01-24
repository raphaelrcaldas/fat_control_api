"""
Testes para o endpoint PUT /users/{user_id}.

Este endpoint permite atualizar dados de um usuário.
Requer permissão 'user:update'.
"""

from datetime import date
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.users import User

pytestmark = pytest.mark.anyio


async def test_update_user_success(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que um usuário com permissão pode atualizar outro usuário.
    """
    token = await make_token(user_with_update_permission)
    _, other_user = users

    update_data = {
        'nome_guerra': 'atualizado',
        'unidade': 'NOVA_UNIDADE',
    }

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {'detail': 'Usuário atualizado com sucesso'}

    # Verifica que os dados foram atualizados no banco
    await session.refresh(other_user)
    db_user = await session.scalar(
        select(User).where(User.id == other_user.id)
    )

    assert db_user.nome_guerra == update_data['nome_guerra']
    assert db_user.unidade == update_data['unidade']


async def test_update_user_partial_update(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que é possível fazer atualização parcial (apenas alguns campos).
    """
    token = await make_token(user_with_update_permission)
    _, other_user = users

    original_nome_guerra = other_user.nome_guerra

    # Atualiza apenas a unidade
    update_data = {'unidade': 'NOVA_UNIDADE'}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(other_user)

    # Verifica que apenas o campo atualizado mudou
    assert other_user.unidade == update_data['unidade']
    assert other_user.nome_guerra == original_nome_guerra


async def test_update_user_without_permission_fails(client, users, make_token):
    """
    Testa que usuário sem permissão não pode atualizar usuários.
    """
    user, other_user = users
    token = await make_token(user)

    update_data = {'nome_guerra': 'atualizado'}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_update_user_not_found(
    client, user_with_update_permission, make_token
):
    """
    Testa que atualizar usuário inexistente retorna 404.
    """
    token = await make_token(user_with_update_permission)

    update_data = {'nome_guerra': 'atualizado'}

    response = await client.put(
        '/users/99999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {'detail': 'User not found'}


async def test_update_user_duplicate_saram_fails(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que não é possível atualizar para um saram já existente.
    """
    token = await make_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o saram de user
    update_data = {'saram': user.saram}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'saram' in response.json()['detail'].lower()


async def test_update_user_duplicate_cpf_fails(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que não é possível atualizar para um CPF já existente.
    """
    token = await make_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o CPF de user
    update_data = {'cpf': user.cpf}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'cpf' in response.json()['detail'].lower()


async def test_update_user_duplicate_id_fab_fails(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que não é possível atualizar para um ID FAB já existente.
    """
    token = await make_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o CPF de user
    update_data = {'id_fab': user.id_fab}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'id fab' in response.json()['detail'].lower()


async def test_update_user_duplicate_zimbra_fails(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que não é possível atualizar para um Zimbra já existente.
    """
    token = await make_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o Zimbra de user
    update_data = {'email_fab': user.email_fab}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'zimbra' in response.json()['detail'].lower()


async def test_update_user_duplicate_email_pessoal_fails(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que não é possível atualizar para um email pessoal já existente.
    """
    token = await make_token(user_with_update_permission)
    user, other_user = users

    # Tenta atualizar other_user para ter o Email pessoal de user
    update_data = {'email_pess': user.email_pess}

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'email pessoal' in response.json()['detail'].lower()


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
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que é possível atualizar outros campos mantendo o mesmo saram/cpf.

    Importante para verificar que a validação de unicidade
    exclui o próprio usuário.
    """
    token = await make_token(user_with_update_permission)
    _, other_user = users

    # Atualiza mantendo o mesmo saram mas mudando outro campo
    update_data = {
        'saram': other_user.saram,  # Mantém o mesmo
        'unidade': 'NOVA_UNIDADE',  # Muda outro campo
    }

    response = await client.put(
        f'/users/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(other_user)
    assert other_user.unidade == 'NOVA_UNIDADE'


async def test_update_user_with_date_field(
    client, session, users, user_with_update_permission, make_token
):
    """
    Testa que é possível atualizar campos do tipo date.

    Este teste garante que a cobertura inclui o código que
    converte datas para isoformat() no log de auditoria.
    """
    token = await make_token(user_with_update_permission)
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
    assert response.json() == {'detail': 'Usuário atualizado com sucesso'}

    # Verifica que a data foi atualizada no banco
    await session.refresh(other_user)
    db_user = await session.scalar(
        select(User).where(User.id == other_user.id)
    )

    assert db_user.nasc == new_birth_date
