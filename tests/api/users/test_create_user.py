"""
Testes para o endpoint POST /users/.

Este endpoint permite criar novos usuários.
Requer permissão 'user:create'.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.shared.users import User

pytestmark = pytest.mark.anyio


async def test_create_user_success(
    client, session, user_with_create_permission, make_org_token
):
    """
    Testa que um usuário com permissão pode criar outro usuário.
    """
    token = await make_org_token(user_with_create_permission)

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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == 'Usuario adicionado com sucesso'
    assert resp['data'] is not None
    assert resp['data']['saram'] == user_data['saram']

    # Verifica que o usuário foi criado no banco
    db_user = await session.scalar(
        select(User).where(User.saram == user_data['saram'])
    )
    assert db_user is not None
    assert db_user.nome_guerra == user_data['nome_guerra']
    assert db_user.first_login is True


async def test_create_user_apenas_obrigatorios(
    client, session, user_with_create_permission, make_org_token
):
    """
    Cadastro enxuto: só os campos NOT NULL do model. Os opcionais em branco
    chegam do formulário como '' ou null e devem virar NULL, não 422.
    """
    token = await make_org_token(user_with_create_permission)

    user_data = {
        'p_g': '2s',
        'nome_guerra': 'minimo',
        'saram': '9876545',
        # Como o formulário envia os campos opcionais não preenchidos:
        'quadro': None,
        'esp': None,
        'nome_completo': '',
        'id_fab': None,
        'cpf': None,
        'telefone': None,
        'email_pess': None,
        'email_fab': None,
        'nasc': '',
        'data_praca': '',
        'ult_promo': '',
        'ant_rel': None,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.CREATED

    db_user = await session.scalar(
        select(User).where(User.saram == user_data['saram'])
    )
    assert db_user is not None
    assert db_user.cpf is None
    assert db_user.nasc is None
    assert db_user.data_praca is None
    assert db_user.ult_promo is None
    assert db_user.nome_completo is None
    assert db_user.ant_rel is None
    # Nasce ativo — `active` não faz parte do payload de cadastro.
    assert db_user.active is True


async def test_create_user_erro_validacao_identifica_campo(
    client, user_with_create_permission, make_org_token
):
    """
    O 422 devolve `errors` como campo → mensagem, para o formulário marcar o
    input culpado em vez de exibir um "Erro de validação" genérico.
    """
    token = await make_org_token(user_with_create_permission)

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'p_g': '2s',
            'nome_guerra': 'fulano',
            'saram': '9876545',
            'cpf': '12345678900',  # DV inválido
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    resp = response.json()
    assert resp['message'] == 'Erro de validação'
    assert 'CPF inválido' in resp['errors']['body.cpf']


async def test_create_user_without_permission_fails(
    client, users, make_org_token
):
    """
    Testa que usuário sem permissão não pode criar usuários.
    """
    user, _ = users
    # ensure_role=False: o teste valida ausência de permissão, então NÃO
    # pode receber a role default (admin) que make_org_token atribuiria.
    token = await make_org_token(user, ensure_role=False)

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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_create_user_duplicate_saram_fails(
    client, session, user_with_create_permission, make_org_token, users
):
    """
    Testa que não é possível criar usuário com saram duplicado.
    """
    token = await make_org_token(user_with_create_permission)
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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'saram' in resp['message'].lower()


async def test_create_user_duplicate_cpf_fails(
    client, session, user_with_create_permission, make_org_token, users
):
    """
    Testa que não é possível criar usuário com CPF duplicado.
    """
    token = await make_org_token(user_with_create_permission)
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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'cpf' in resp['message'].lower()


async def test_create_user_duplicate_id_fab_fails(
    client, session, user_with_create_permission, make_org_token, users
):
    """
    Testa que não é possível criar usuário com ID FAB duplicado.
    """
    token = await make_org_token(user_with_create_permission)
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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'id fab' in resp['message'].lower()


async def test_create_user_duplicate_zimbra_fails(
    client, session, user_with_create_permission, make_org_token, users
):
    """
    Testa que não é possível criar usuário com Zimbra duplicado.
    """
    token = await make_org_token(user_with_create_permission)
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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.mil.br',
        'email_fab': existing_user.email_fab,
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'zimbra' in resp['message'].lower()


async def test_create_user_duplicate_email_pess_fails(
    client, session, user_with_create_permission, make_org_token, users
):
    """
    Testa que não é possível criar usuário com Email pessoal duplicado.
    """
    token = await make_org_token(user_with_create_permission)
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
        'data_praca': '2015-03-10',
        'email_pess': existing_user.email_pess,
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'email pessoal' in resp['message'].lower()


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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post('/users/', json=user_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_user_with_invalid_data_fails(
    client, user_with_create_permission, make_org_token
):
    """
    Testa que criação com dados inválidos é rejeitada.
    """
    token = await make_org_token(user_with_create_permission)

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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_user_with_invalid_saram_dv_fails(
    client, user_with_create_permission, make_org_token
):
    """
    Testa que criação com SARAM com dígito verificador incorreto é rejeitada.
    """
    token = await make_org_token(user_with_create_permission)

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
        'data_praca': '2015-03-10',
        'email_pess': 'novo@email.com',
        'email_fab': 'novo@fab.mil.br',
        'active': True,
        'unidade': '11gt',
        'ant_rel': 100,
    }

    response = await client.post(
        '/users/',
        headers={'Authorization': f'Bearer {token}'},
        json=user_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    resp = response.json()
    assert resp['status'] == 'error'
    # Verifica que o erro menciona SARAM ou dígito verificador
    assert resp['errors'] is not None
