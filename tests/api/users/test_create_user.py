"""
Testes para o endpoint POST /users/.

Este endpoint permite criar novos usuários.
Requer permissão 'user:create'.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.users import User

pytestmark = pytest.mark.anyio


async def test_create_user_success(
    client, session, user_with_create_permission, make_token
):
    """
    Testa que um usuário com permissão pode criar outro usuário.
    """
    token = await make_token(user_with_create_permission)

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123456',
        'saram': '9876545',  # SARAM válido com DV correto
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {'detail': 'Usuário Adicionado com sucesso'}

    # Verifica que o usuário foi criado no banco
    db_user = await session.scalar(
        select(User).where(User.saram == user_data['saram'])
    )
    assert db_user is not None
    assert db_user.nome_guerra == user_data['nome_guerra']
    assert db_user.first_login is True


async def test_create_user_without_permission_fails(client, users, make_token):
    """
    Testa que usuário sem permissão não pode criar usuários.
    """
    user, _ = users
    token = await make_token(user)

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123456',
        'saram': '9876545',  # SARAM válido com DV correto
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_create_user_duplicate_saram_fails(
    client, session, user_with_create_permission, make_token, users
):
    """
    Testa que não é possível criar usuário com saram duplicado.
    """
    token = await make_token(user_with_create_permission)
    existing_user, _ = users

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123456',
        'saram': existing_user.saram,  # Saram duplicado
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'saram' in response.json()['detail'].lower()


async def test_create_user_duplicate_cpf_fails(
    client, session, user_with_create_permission, make_token, users
):
    """
    Testa que não é possível criar usuário com CPF duplicado.
    """
    token = await make_token(user_with_create_permission)
    existing_user, _ = users

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123457',
        'saram': '9876545',  # SARAM válido com DV correto
        'cpf': existing_user.cpf,  # CPF duplicado
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'cpf' in response.json()['detail'].lower()


async def test_create_user_duplicate_id_fab_fails(
    client, session, user_with_create_permission, make_token, users
):
    """
    Testa que não é possível criar usuário com ID FAB duplicado.
    """
    token = await make_token(user_with_create_permission)
    existing_user, _ = users

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': existing_user.id_fab,
        'saram': '9876545',
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'id fab' in response.json()['detail'].lower()


async def test_create_user_duplicate_zimbra_fails(
    client, session, user_with_create_permission, make_token, users
):
    """
    Testa que não é possível criar usuário com Zimbra duplicado.
    """
    token = await make_token(user_with_create_permission)
    existing_user, _ = users

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123457',
        'saram': '9876545',
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.mil.br',
        'email_fab': existing_user.email_fab,
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'zimbra' in response.json()['detail'].lower()


async def test_create_user_duplicate_email_pess_fails(
    client, session, user_with_create_permission, make_token, users
):
    """
    Testa que não é possível criar usuário com Email pessoal duplicado.
    """
    token = await make_token(user_with_create_permission)
    existing_user, _ = users

    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123457',
        'saram': '9876545',
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': existing_user.email_pess,
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'email pessoal' in response.json()['detail'].lower()


async def test_create_user_without_token_fails(client):
    """
    Testa que requisição sem token é rejeitada.
    """
    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123456',
        'saram': '9876545',
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post('/users/', json=user_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_user_with_invalid_data_fails(
    client, user_with_create_permission, make_token
):
    """
    Testa que criação com dados inválidos é rejeitada.
    """
    token = await make_token(user_with_create_permission)

    # Saram inválido (muito curto)
    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123456',
        'saram': '123',  # Inválido (muito curto)
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_user_with_invalid_saram_dv_fails(
    client, user_with_create_permission, make_token
):
    """
    Testa que criação com SARAM com dígito verificador incorreto é rejeitada.
    """
    token = await make_token(user_with_create_permission)

    # SARAM com DV incorreto (deveria ser 5, mas está como 3)
    user_data = {
        'p_g': '2s',
        'esp': 'inf',
        'nome_guerra': 'novo_usuario',
        'nome_completo': 'Novo Usuario da Silva',
        'id_fab': '123456',
        'saram': '9876543',  # DV incorreto (correto seria 9876545)
        'cpf': '52998224725',
        'ult_promo': '2020-01-15',
        'nasc': '1990-05-20',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': 'TEST',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    response_data = response.json()
    assert 'detail' in response_data
    # Verifica que o erro menciona SARAM ou dígito verificador
    error_detail = str(response_data['detail']).lower()
    assert 'saram' in error_detail or 'verificador' in error_detail
