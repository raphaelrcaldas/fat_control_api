"""
Testes para o endpoint POST /cegep/dados-bancarios/.

Este endpoint cria novos dados bancarios para um usuario.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios

pytestmark = pytest.mark.anyio


async def test_create_dados_bancarios_success(client, session, users, token):
    """Testa criacao de dados bancarios com sucesso."""
    _, other_user = users

    dados_data = {
        'user_id': other_user.id,
        'banco': 'Banco do Brasil',
        'codigo_banco': '001',
        'agencia': '1234-5',
        'conta': '12345-6',
    }

    response = await client.post(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
        json=dados_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()
    assert data['status'] == 'success'
    assert data['message'] == 'Dados bancários criados com sucesso'
    assert 'id' in data['data']

    # Verifica no banco
    db_dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.user_id == other_user.id)
    )
    assert db_dados is not None
    assert db_dados.banco == 'Banco do Brasil'
    assert db_dados.codigo_banco == '001'
    assert db_dados.agencia == '1234-5'
    assert db_dados.conta == '12345-6'


async def test_create_dados_bancarios_user_not_found(client, token):
    """Testa que criacao com user_id inexistente falha."""
    dados_data = {
        'user_id': 999999,
        'banco': 'Banco Teste',
        'codigo_banco': '999',
        'agencia': '0000-0',
        'conta': '00000-0',
    }

    response = await client.post(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
        json=dados_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Usuário não encontrado' in response.json()['message']


async def test_create_dados_bancarios_duplicate_user(
    client, session, users, token, dados_bancarios
):
    """Testa que apenas 1 registro por usuario e permitido."""
    user, _ = users

    # dados_bancarios ja existe para user (via fixture)
    dados_data = {
        'user_id': user.id,
        'banco': 'Outro Banco',
        'codigo_banco': '002',
        'agencia': '5678-9',
        'conta': '67890-1',
    }

    response = await client.post(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
        json=dados_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Já existem dados bancários' in response.json()['message']


async def test_create_dados_bancarios_without_token(client, users):
    """Testa que requisicao sem token falha."""
    _, other_user = users

    dados_data = {
        'user_id': other_user.id,
        'banco': 'Banco Teste',
        'codigo_banco': '001',
        'agencia': '1234-5',
        'conta': '12345-6',
    }

    response = await client.post('/cegep/dados-bancarios/', json=dados_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_dados_bancarios_missing_required_field(
    client, users, token
):
    """Testa que campo obrigatorio faltando falha."""
    _, other_user = users

    # Falta o campo 'conta'
    dados_data = {
        'user_id': other_user.id,
        'banco': 'Banco Teste',
        'codigo_banco': '001',
        'agencia': '1234-5',
    }

    response = await client.post(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
        json=dados_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
