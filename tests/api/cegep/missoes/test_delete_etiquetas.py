"""
Testes para o endpoint DELETE /cegep/missoes/etiquetas/{id}.

Este endpoint remove uma etiqueta.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.missoes import Etiqueta

pytestmark = pytest.mark.anyio


async def test_delete_etiqueta_success(
    client, session, token, etiqueta_existente
):
    """Testa remocao de etiqueta com sucesso."""
    etiqueta_id = etiqueta_existente.id

    response = await client.delete(
        f'/cegep/missoes/etiquetas/{etiqueta_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'removida' in resp['message'].lower()

    # Verifica que foi removida do banco
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == etiqueta_id)
    )
    assert db_etiqueta is None


async def test_delete_etiqueta_not_found(client, token):
    """Testa remocao de etiqueta inexistente."""
    response = await client.delete(
        '/cegep/missoes/etiquetas/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrada' in response.json()['message'].lower()


async def test_delete_etiqueta_without_token(client, etiqueta_existente):
    """Testa que requisicao sem token falha."""
    response = await client.delete(
        f'/cegep/missoes/etiquetas/{etiqueta_existente.id}'
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
