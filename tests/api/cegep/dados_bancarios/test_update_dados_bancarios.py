"""
Testes para o endpoint PUT /cegep/dados-bancarios/{dados_id}.

Este endpoint atualiza dados bancarios existentes.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_update_dados_bancarios_success(
    client, session, token, dados_bancarios
):
    """Testa atualizacao de dados bancarios com sucesso."""
    update_data = {
        'banco': 'Caixa Economica',
        'codigo_banco': '104',
        'agencia': '9876-5',
        'conta': '98765-4',
    }

    response = await client.put(
        f'/cegep/dados-bancarios/{dados_bancarios.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    assert 'atualizados com sucesso' in response.json()['detail']

    # Verifica no banco
    await session.refresh(dados_bancarios)
    assert dados_bancarios.banco == 'Caixa Economica'
    assert dados_bancarios.codigo_banco == '104'
    assert dados_bancarios.agencia == '9876-5'
    assert dados_bancarios.conta == '98765-4'


async def test_update_dados_bancarios_partial(
    client, session, token, dados_bancarios
):
    """Testa atualizacao parcial de dados bancarios."""
    original_banco = dados_bancarios.banco

    update_data = {
        'agencia': '1111-1',
    }

    response = await client.put(
        f'/cegep/dados-bancarios/{dados_bancarios.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que apenas agencia foi alterada
    await session.refresh(dados_bancarios)
    assert dados_bancarios.banco == original_banco
    assert dados_bancarios.agencia == '1111-1'


async def test_update_dados_bancarios_not_found(client, token):
    """Testa atualizacao de dados bancarios inexistente."""
    update_data = {
        'banco': 'Banco Teste',
    }

    response = await client.put(
        '/cegep/dados-bancarios/999999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Dados bancários não encontrados' in response.json()['detail']


async def test_update_dados_bancarios_without_token(client, dados_bancarios):
    """Testa que requisicao sem token falha."""
    update_data = {
        'banco': 'Banco Teste',
    }

    response = await client.put(
        f'/cegep/dados-bancarios/{dados_bancarios.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_dados_bancarios_empty_body(
    client, session, token, dados_bancarios
):
    """Testa atualizacao com body vazio nao altera nada."""
    original_banco = dados_bancarios.banco
    original_agencia = dados_bancarios.agencia

    response = await client.put(
        f'/cegep/dados-bancarios/{dados_bancarios.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que nada foi alterado
    await session.refresh(dados_bancarios)
    assert dados_bancarios.banco == original_banco
    assert dados_bancarios.agencia == original_agencia
