"""
Testes para o endpoint POST /ops/trips/func/.

Este endpoint cria uma nova função para um tripulante.
"""

from http import HTTPStatus

import pytest

from tests.factories import FuncFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio


async def test_create_funcao_success(client, trip, org_admin_token):
    """Testa criação de função com sucesso."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2024-01-15',
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()

    assert resp['status'] == 'success'
    assert 'message' in resp
    assert resp['message'] == 'Função cadastrada com sucesso'


async def test_create_funcao_without_data_op(client, trip, org_admin_token):
    """Testa criação de função sem data de operacionalidade."""
    func_data = {
        'func': 'mc',
        'oper': 'ba',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()

    assert resp['status'] == 'success'
    assert resp['message'] == 'Função cadastrada com sucesso'


async def test_create_funcao_trip_not_found(client, org_admin_token):
    """Testa que retorna erro para tripulante inexistente."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': 99999},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Tripulante não encontrado'


async def test_create_funcao_duplicate_fails(
    client, session, trip, org_admin_token
):
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
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Função já registrada para esse tripulante'


async def test_create_funcao_different_func_allowed(
    client, session, trip, org_admin_token
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
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_funcao_invalid_func_fails(client, trip, org_admin_token):
    """Testa que função inválida falha na validação."""
    func_data = {
        'func': 'invalid',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_invalid_oper_fails(client, trip, org_admin_token):
    """Testa que operacionalidade inválida falha na validação."""
    func_data = {
        'func': 'pil',
        'oper': 'invalid',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_invalid_proj_fails(client, trip, org_admin_token):
    """Testa que projeto inválido falha na validação."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'invalid',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_missing_func_fails(client, trip, org_admin_token):
    """Testa que func é obrigatório."""
    func_data = {
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_other_org_trip_not_found(
    client, session, org_admin_token
):
    """Tripulante de outra UAE é invisível para a org ativa (400).

    O token é da org '11gt'; o tripulante pertence a '1gt'. Criar função
    nele deve responder 'Tripulante não encontrado'.
    """
    other_user = UserFactory()
    session.add(other_user)
    await session.commit()
    await session.refresh(other_user)

    other_trip = TripFactory(user_id=other_user.id, uae='1gt')
    session.add(other_trip)
    await session.commit()
    await session.refresh(other_trip)

    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': other_trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Tripulante não encontrado'


async def test_create_funcao_missing_active_org_fails(client, trip, token):
    """Sem org ativa no token, criar função responde 400."""
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


async def test_create_funcao_without_token_fails(client, trip):
    """Sem autenticação, o endpoint responde 401."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_funcao_missing_oper_fails(client, trip, org_admin_token):
    """Testa que oper é obrigatório."""
    func_data = {
        'func': 'pil',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_funcao_missing_proj_fails(client, trip, org_admin_token):
    """Testa que proj é obrigatório."""
    func_data = {
        'func': 'pil',
        'oper': 'op',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/func/',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        params={'trip_id': trip.id},
        json=func_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
