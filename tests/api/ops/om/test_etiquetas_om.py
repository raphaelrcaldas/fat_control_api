"""
Testes para os endpoints CRUD de etiquetas de OM.

GET    /ops/om/etiquetas/      - Listar etiquetas
POST   /ops/om/etiquetas/      - Criar etiqueta
PUT    /ops/om/etiquetas/{id}  - Atualizar etiqueta
DELETE /ops/om/etiquetas/{id}  - Deletar etiqueta
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.public.om import Etiqueta

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om/etiquetas/'


# ===============================================================
# GET /ops/om/etiquetas/ - Listar
# ===============================================================


async def test_list_etiquetas_empty(client, session, token):
    """Listagem sem etiquetas retorna lista vazia."""
    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_list_etiquetas_returns_items(
    client, session, token
):
    """Listagem retorna etiquetas existentes."""
    etq = Etiqueta(
        nome='Tag1', cor='#FF0000', descricao='desc1'
    )
    session.add(etq)
    await session.commit()

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['nome'] == 'Tag1'
    assert resp['data'][0]['cor'] == '#FF0000'


async def test_list_etiquetas_ordered_by_nome(
    client, session, token
):
    """Etiquetas sao retornadas ordenadas por nome."""
    session.add(
        Etiqueta(nome='Zebra', cor='#000000')
    )
    session.add(
        Etiqueta(nome='Alpha', cor='#FFFFFF')
    )
    await session.commit()

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert len(data) == 2
    assert data[0]['nome'] == 'Alpha'
    assert data[1]['nome'] == 'Zebra'


async def test_list_etiquetas_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.get(BASE_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ===============================================================
# POST /ops/om/etiquetas/ - Criar
# ===============================================================


async def test_create_etiqueta_success(
    client, session, token
):
    """Criacao de etiqueta com dados validos."""
    payload = {
        'nome': 'Nova Tag',
        'cor': '#00FF00',
        'descricao': 'Nova descricao',
    }

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['nome'] == 'Nova Tag'
    assert data['cor'] == '#00FF00'
    assert data['descricao'] == 'Nova descricao'
    assert 'id' in data


async def test_create_etiqueta_without_descricao(
    client, session, token
):
    """Criacao de etiqueta sem descricao (campo opcional)."""
    payload = {'nome': 'Simples', 'cor': '#0000FF'}

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert data['nome'] == 'Simples'
    assert data['descricao'] is None


async def test_create_etiqueta_requires_auth(client):
    """Endpoint requer autenticacao."""
    payload = {'nome': 'Test', 'cor': '#FF0000'}
    response = await client.post(BASE_URL, json=payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ===============================================================
# PUT /ops/om/etiquetas/{id} - Atualizar
# ===============================================================


async def test_update_etiqueta_success(
    client, session, token
):
    """Atualizacao parcial de etiqueta funciona."""
    etq = Etiqueta(
        nome='Original', cor='#FF0000', descricao='old'
    )
    session.add(etq)
    await session.commit()
    await session.refresh(etq)

    response = await client.put(
        f'{BASE_URL}{etq.id}',
        json={'nome': 'Atualizada'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['nome'] == 'Atualizada'
    assert data['cor'] == '#FF0000'
    assert data['descricao'] == 'old'


async def test_update_etiqueta_all_fields(
    client, session, token
):
    """Atualizacao de todos os campos funciona."""
    etq = Etiqueta(
        nome='Original', cor='#FF0000', descricao='old'
    )
    session.add(etq)
    await session.commit()
    await session.refresh(etq)

    response = await client.put(
        f'{BASE_URL}{etq.id}',
        json={
            'nome': 'Nova',
            'cor': '#00FF00',
            'descricao': 'new',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['nome'] == 'Nova'
    assert data['cor'] == '#00FF00'
    assert data['descricao'] == 'new'


async def test_update_etiqueta_not_found(
    client, session, token
):
    """Atualizacao de etiqueta inexistente retorna 404."""
    response = await client.put(
        f'{BASE_URL}99999',
        json={'nome': 'Nova'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_etiqueta_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.put(
        f'{BASE_URL}1', json={'nome': 'Test'}
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ===============================================================
# DELETE /ops/om/etiquetas/{id} - Deletar
# ===============================================================


async def test_delete_etiqueta_success(
    client, session, token
):
    """Delecao de etiqueta existente funciona (hard delete)."""
    etq = Etiqueta(
        nome='Deletar', cor='#FF0000', descricao='bye'
    )
    session.add(etq)
    await session.commit()
    await session.refresh(etq)

    response = await client.delete(
        f'{BASE_URL}{etq.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'

    deleted = await session.get(Etiqueta, etq.id)
    assert deleted is None


async def test_delete_etiqueta_not_found(
    client, session, token
):
    """Delecao de etiqueta inexistente retorna 404."""
    response = await client.delete(
        f'{BASE_URL}99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_delete_etiqueta_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.delete(f'{BASE_URL}1')
    assert response.status_code == HTTPStatus.UNAUTHORIZED
