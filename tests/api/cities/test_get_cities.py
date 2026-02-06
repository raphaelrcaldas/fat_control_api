"""
Testes para o endpoint GET /cities/.

Este endpoint busca cidades por nome (search).
Requer autenticacao.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_get_cities_success(client, token):
    """Testa busca de cidades com sucesso."""
    response = await client.get(
        '/cities/?search=Paulo',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    data = resp['data']

    assert isinstance(data, list)
    assert len(data) > 0


async def test_get_cities_returns_matching_cities(client, token):
    """Testa que retorna cidades que correspondem ao termo."""
    response = await client.get(
        '/cities/?search=Rio',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    data = resp['data']

    # Deve encontrar Rio de Janeiro
    nomes = [c['nome'] for c in data]
    assert any('Rio' in nome for nome in nomes)


async def test_get_cities_case_insensitive(client, token):
    """Testa que a busca e case insensitive."""
    response_lower = await client.get(
        '/cities/?search=brasilia',
        headers={'Authorization': f'Bearer {token}'},
    )
    response_upper = await client.get(
        '/cities/?search=BRASILIA',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response_lower.status_code == HTTPStatus.OK
    assert response_upper.status_code == HTTPStatus.OK

    data_lower = response_lower.json()['data']
    data_upper = response_upper.json()['data']

    assert len(data_lower) == len(data_upper)


async def test_get_cities_no_results(client, token):
    """Testa que busca sem resultados retorna lista vazia."""
    response = await client.get(
        '/cities/?search=XYZNaoExiste123',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    data = resp['data']

    assert isinstance(data, list)
    assert len(data) == 0


async def test_get_cities_response_schema(client, token):
    """Testa o schema da resposta (modelo Cidade)."""
    response = await client.get(
        '/cities/?search=Paulo',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    data = resp['data']

    assert len(data) > 0
    cidade = data[0]

    assert isinstance(cidade['codigo'], int)
    assert isinstance(cidade['nome'], str)
    assert isinstance(cidade['uf'], str)


async def test_get_cities_limit_20(client, token):
    """Testa que o limite maximo e 20 resultados."""
    # Busca genérica que pode retornar muitos resultados
    response = await client.get(
        '/cities/?search=a',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    data = resp['data']

    assert len(data) <= 20


async def test_get_cities_missing_search_fails(client, token):
    """Testa que requisicao sem parametro search falha."""
    response = await client.get(
        '/cities/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_get_cities_without_token_fails(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cities/?search=Paulo')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
