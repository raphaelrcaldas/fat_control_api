"""
Testes para o endpoint PUT /ops/trips/func/{id}.

Este endpoint atualiza uma função existente.
"""

from http import HTTPStatus

import pytest

from tests.factories import FuncFactory

pytestmark = pytest.mark.anyio


async def test_update_funcao_success(client, funcao, token):
    """Testa atualização de função com sucesso."""
    update_data = {
        'oper': 'op',
        'data_op': '2024-06-15',
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert 'message' in resp
    assert resp['message'] == 'Função atualizada com sucesso'


async def test_update_funcao_change_oper(client, funcao, token):
    """Testa alteração da operacionalidade."""
    update_data = {
        'oper': 'ba',
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_change_data_op(client, funcao, token):
    """Testa alteração da data de operacionalidade."""
    update_data = {
        'oper': funcao.oper,
        'data_op': '2024-12-31',
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_set_data_op_to_null(client, funcao, token):
    """Testa que pode definir data_op como null."""
    update_data = {
        'oper': funcao.oper,
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_not_found(client, token):
    """Testa que retorna 404 para função inexistente."""
    update_data = {
        'oper': 'op',
        'data_op': None,
    }

    response = await client.put(
        '/ops/trips/func/99999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Função não encontrada'


async def test_update_funcao_invalid_oper_fails(client, funcao, token):
    """Testa que operacionalidade inválida falha na validação."""
    update_data = {
        'oper': 'invalid',
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_funcao_oper_only_without_data_op(client, funcao, token):
    """Testa atualização com oper e sem data_op (None)."""
    update_data = {
        'oper': 'in',
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_all_oper_values(client, session, trips, token):
    """Testa que todas as operacionalidades válidas são aceitas."""
    trip, _ = trips
    opers = ['ba', 'op', 'in', 'al']

    for oper_value in opers:
        func = FuncFactory(trip_id=trip.id)
        session.add(func)
        await session.commit()
        await session.refresh(func)

        update_data = {
            'oper': oper_value,
            'data_op': None,
        }

        response = await client.put(
            f'/ops/trips/func/{func.id}',
            headers={'Authorization': f'Bearer {token}'},
            json=update_data,
        )

        assert response.status_code == HTTPStatus.OK
