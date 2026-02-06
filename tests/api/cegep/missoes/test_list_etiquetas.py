"""
Testes para o endpoint GET /cegep/missoes/etiquetas.

Este endpoint lista todas as etiquetas disponíveis.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_list_etiquetas_success(client, token, etiquetas_lista):
    """Testa listagem de etiquetas com sucesso."""
    response = await client.get(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert len(resp['data']) == 3


async def test_list_etiquetas_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/missoes/etiquetas')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_list_etiquetas_empty(client, token):
    """Testa listagem quando nao ha etiquetas."""
    response = await client.get(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_list_etiquetas_ordered_by_nome(client, token, etiquetas_lista):
    """Testa que etiquetas sao retornadas ordenadas por nome."""
    response = await client.get(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    nomes = [e['nome'] for e in resp['data']]
    assert nomes == sorted(nomes)
