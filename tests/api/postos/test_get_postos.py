"""
Testes para o endpoint GET /postos/.

Este endpoint lista todos os postos/graduacoes.
Requer autenticacao.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.enums.posto_grad import PostoGradEnum

pytestmark = pytest.mark.anyio


async def test_get_postos_success(client, token):
    """Testa listagem de postos com sucesso."""
    response = await client.get(
        '/postos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    assert isinstance(data, list)


async def test_get_postos_returns_all_postos(client, token):
    """Testa que retorna todos os postos do seed."""
    response = await client.get(
        '/postos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    assert len(data) == len(PostoGradEnum)


async def test_get_postos_response_schema(client, token):
    """Testa o schema da resposta (PostoGradSchema)."""
    response = await client.get(
        '/postos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    for posto in data:
        assert isinstance(posto['ant'], int)
        assert isinstance(posto['short'], str)
        assert isinstance(posto['mid'], str)
        assert isinstance(posto['long'], str)
        assert isinstance(posto['circulo'], str)


async def test_get_postos_contains_all_enum_values(client, token):
    """Testa que todos os valores do PostoGradEnum estao presentes."""
    response = await client.get(
        '/postos/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    shorts = {p['short'] for p in data}
    expected = {pg.value for pg in PostoGradEnum}

    assert shorts == expected, (
        f'Postos divergem do enum. '
        f'Faltando: {expected - shorts}, Extras: {shorts - expected}'
    )


async def test_get_postos_without_token_fails(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/postos/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
