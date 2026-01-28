"""
Testes para o endpoint DELETE /cegep/soldos/{soldo_id}.

Este endpoint deleta um soldo existente.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.posto_grad import Soldo

pytestmark = pytest.mark.anyio


async def test_delete_soldo_success(client, session, token, soldos):
    """Testa delecao de soldo com sucesso."""
    soldo = soldos[0]
    soldo_id = soldo.id

    response = await client.delete(
        f'/cegep/soldos/{soldo_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert 'deletado com sucesso' in response.json()['detail']

    # Verifica no banco
    db_soldo = await session.scalar(
        select(Soldo).where(Soldo.id == soldo_id)
    )
    assert db_soldo is None


async def test_delete_soldo_not_found(client, token):
    """Testa delecao de soldo inexistente."""
    response = await client.delete(
        '/cegep/soldos/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Soldo nao encontrado' in response.json()['detail']


async def test_delete_soldo_without_token(client, soldos):
    """Testa que requisicao sem token falha."""
    soldo = soldos[0]

    response = await client.delete(f'/cegep/soldos/{soldo.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
