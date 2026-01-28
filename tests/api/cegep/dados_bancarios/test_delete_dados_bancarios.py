"""
Testes para o endpoint DELETE /cegep/dados-bancarios/{dados_id}.

Este endpoint deleta dados bancarios existentes.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios

pytestmark = pytest.mark.anyio


async def test_delete_dados_bancarios_success(
    client, session, token, dados_bancarios
):
    """Testa delecao de dados bancarios com sucesso."""
    dados_id = dados_bancarios.id

    response = await client.delete(
        f'/cegep/dados-bancarios/{dados_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert 'deletados com sucesso' in response.json()['detail']

    # Verifica no banco
    db_dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.id == dados_id)
    )
    assert db_dados is None


async def test_delete_dados_bancarios_not_found(client, token):
    """Testa delecao de dados bancarios inexistente."""
    response = await client.delete(
        '/cegep/dados-bancarios/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Dados bancários não encontrados' in response.json()['detail']


async def test_delete_dados_bancarios_without_token(client, dados_bancarios):
    """Testa que requisicao sem token falha."""
    response = await client.delete(
        f'/cegep/dados-bancarios/{dados_bancarios.id}'
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_delete_dados_bancarios_allows_new_creation(
    client, session, users, token, dados_bancarios
):
    """Testa que apos deletar, usuario pode criar novos dados."""
    user, _ = users
    dados_id = dados_bancarios.id

    # Deleta os dados bancarios
    response = await client.delete(
        f'/cegep/dados-bancarios/{dados_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    # Cria novos dados bancarios para o mesmo usuario
    new_dados = {
        'user_id': user.id,
        'banco': 'Novo Banco',
        'codigo_banco': '999',
        'agencia': '9999-9',
        'conta': '99999-9',
    }

    response = await client.post(
        '/cegep/dados-bancarios/',
        headers={'Authorization': f'Bearer {token}'},
        json=new_dados,
    )

    assert response.status_code == HTTPStatus.CREATED

    # Verifica no banco
    db_dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.user_id == user.id)
    )
    assert db_dados is not None
    assert db_dados.banco == 'Novo Banco'
