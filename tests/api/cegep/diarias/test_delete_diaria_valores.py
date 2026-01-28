"""
Testes para o endpoint DELETE /cegep/diarias/valores/{valor_id}.

Este endpoint deleta um valor de diaria existente.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.diarias import DiariaValor

pytestmark = pytest.mark.anyio


async def test_delete_diaria_valor_success(
    client, session, token, diaria_valores
):
    """Testa delecao de valor de diaria com sucesso."""
    valor = diaria_valores[0]
    valor_id = valor.id

    response = await client.delete(
        f'/cegep/diarias/valores/{valor_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert 'deletado com sucesso' in response.json()['detail']

    # Verifica no banco
    db_valor = await session.scalar(
        select(DiariaValor).where(DiariaValor.id == valor_id)
    )
    assert db_valor is None


async def test_delete_diaria_valor_not_found(client, token):
    """Testa delecao de valor de diaria inexistente."""
    response = await client.delete(
        '/cegep/diarias/valores/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrado' in response.json()['detail']


async def test_delete_diaria_valor_without_token(client, diaria_valores):
    """Testa que requisicao sem token falha."""
    valor = diaria_valores[0]

    response = await client.delete(f'/cegep/diarias/valores/{valor.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
