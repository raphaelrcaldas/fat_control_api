"""
Testes para o endpoint DELETE /nav/aerodromos/{id}.

Este endpoint deleta um aerodromo existente.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.nav.aerodromos import Aerodromo

pytestmark = pytest.mark.anyio


async def test_delete_aerodromo_success(client, session, token, aerodromos):
    """Testa delecao de aerodromo com sucesso."""
    aerodromo = aerodromos[0]
    aerodromo_id = aerodromo.id

    response = await client.delete(
        f'/nav/aerodromos/{aerodromo_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'deletado com sucesso' in resp['message']

    # Verifica no banco
    db_aerodromo = await session.scalar(
        select(Aerodromo).where(Aerodromo.id == aerodromo_id)
    )
    assert db_aerodromo is None


async def test_delete_aerodromo_not_found(client, token):
    """Testa delecao de aerodromo inexistente."""
    response = await client.delete(
        '/nav/aerodromos/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'não encontrado' in resp['message']


async def test_delete_aerodromo_without_token(client, aerodromos):
    """Testa que requisicao sem token falha."""
    aerodromo = aerodromos[0]

    response = await client.delete(f'/nav/aerodromos/{aerodromo.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
