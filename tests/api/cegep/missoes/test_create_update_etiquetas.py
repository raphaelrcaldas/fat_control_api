"""
Testes para o endpoint POST /cegep/missoes/etiquetas.

Este endpoint cria ou atualiza etiquetas.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.missoes import Etiqueta

pytestmark = pytest.mark.anyio


async def test_create_etiqueta_success(client, session, token):
    """Testa criacao de etiqueta com sucesso."""
    payload = {
        'nome': 'Nova Etiqueta',
        'cor': '#FF5500',
    }

    response = await client.post(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'criada' in resp['message'].lower()

    data = resp['data']
    assert data['nome'] == 'Nova Etiqueta'
    assert data['cor'] == '#FF5500'
    assert data['descricao'] is None
    assert 'id' in data

    # Verifica no banco
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == data['id'])
    )
    assert db_etiqueta is not None
    assert db_etiqueta.nome == 'Nova Etiqueta'


async def test_create_etiqueta_without_token(client):
    """Testa que requisicao sem token falha."""
    payload = {'nome': 'Teste', 'cor': '#FF0000'}

    response = await client.post('/cegep/missoes/etiquetas', json=payload)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_etiqueta_missing_nome(client, token):
    """Testa que falta de nome falha."""
    payload = {'cor': '#FF0000'}

    response = await client.post(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_etiqueta_missing_cor(client, token):
    """Testa que falta de cor falha."""
    payload = {'nome': 'Etiqueta sem cor'}

    response = await client.post(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_etiqueta_success(
    client, session, token, etiqueta_existente
):
    """Testa atualizacao de etiqueta com sucesso."""
    payload = {
        'id': etiqueta_existente.id,
        'nome': 'Etiqueta Atualizada',
        'cor': '#00FF00',
        'descricao': 'Nova descricao',
    }

    response = await client.post(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'atualizada' in resp['message'].lower()

    data = resp['data']
    assert data['id'] == etiqueta_existente.id
    assert data['nome'] == 'Etiqueta Atualizada'
    assert data['cor'] == '#00FF00'
    assert data['descricao'] == 'Nova descricao'

    # Verifica no banco
    await session.refresh(etiqueta_existente)
    assert etiqueta_existente.nome == 'Etiqueta Atualizada'


async def test_update_etiqueta_not_found(client, token):
    """Testa atualizacao de etiqueta inexistente."""
    payload = {
        'id': 99999,
        'nome': 'Etiqueta Inexistente',
        'cor': '#FF0000',
    }

    response = await client.post(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrada' in response.json()['message'].lower()


async def test_create_etiqueta_with_descricao(client, session, token):
    """Testa criacao de etiqueta com descricao."""
    payload = {
        'nome': 'Etiqueta Completa',
        'cor': '#0000FF',
        'descricao': 'Descricao completa da etiqueta',
    }

    response = await client.post(
        '/cegep/missoes/etiquetas',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    data = resp['data']
    assert data['descricao'] == 'Descricao completa da etiqueta'

    # Verifica no banco
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == data['id'])
    )
    assert db_etiqueta.descricao == 'Descricao completa da etiqueta'
