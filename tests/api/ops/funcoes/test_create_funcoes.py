"""
Testes para o endpoint POST /ops/trips/func/.

Este endpoint cria uma nova função para um tripulante.
"""

from http import HTTPStatus

import pytest

from tests.factories import FuncFactory

pytestmark = pytest.mark.anyio


async def test_create_funcao_success(client, trip, token):
    """Testa criação de função com sucesso."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2024-01-15',
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert 'detail' in data
    assert data['detail'] == 'Função cadastrada com sucesso'


async def test_create_funcao_without_data_op(client, trip, token):
    """Testa criação de função sem data de operacionalidade."""
    func_data = {
        'func': 'mc',
        'oper': 'ba',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['detail'] == 'Função cadastrada com sucesso'


async def test_create_funcao_trip_not_found(client, token):
    """Testa que retorna erro para tripulante inexistente."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': 99999},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data['detail'] == 'Crew member not found'


async def test_create_funcao_duplicate_fails(client, session, trip, token):
    """Testa que não permite função duplicada para o mesmo tripulante."""
    # Cria uma função existente
    existing_func = FuncFactory(trip_id=trip.id, func='pil')
    session.add(existing_func)
    await session.commit()

    # Tenta criar outra função com o mesmo tipo
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data['detail'] == 'Função já registrada para esse tripulante'


async def test_create_funcao_different_func_allowed(
    client, session, trip, token
):
    """Testa que permite funções diferentes para o mesmo tripulante."""
    # Cria uma função existente
    existing_func = FuncFactory(trip_id=trip.id, func='pil')
    session.add(existing_func)
    await session.commit()

    # Cria outra função com tipo diferente
    func_data = {
        'func': 'mc',
        'oper': 'ba',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_funcao_invalid_func_fails(client, trip, token):
    """Testa que função inválida falha na validação."""
    func_data = {
        'func': 'invalid',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_invalid_oper_fails(client, trip, token):
    """Testa que operacionalidade inválida falha na validação."""
    func_data = {
        'func': 'pil',
        'oper': 'invalid',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_invalid_proj_fails(client, trip, token):
    """Testa que projeto inválido falha na validação."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'invalid',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_missing_func_fails(client, trip, token):
    """Testa que func é obrigatório."""
    func_data = {
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_missing_oper_fails(client, trip, token):
    """Testa que oper é obrigatório."""
    func_data = {
        'func': 'pil',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_missing_proj_fails(client, trip, token):
    """Testa que proj é obrigatório."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
