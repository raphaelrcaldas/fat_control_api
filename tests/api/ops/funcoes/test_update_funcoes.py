"""
Testes para o endpoint PUT /ops/trips/func/{id}.

Este endpoint atualiza uma função existente.
"""

from http import HTTPStatus

import pytest

from tests.factories import FuncFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio


async def _make_foreign_func(session, uae='1gt'):
    """Cria uma função vinculada a um tripulante de outra UAE."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip = TripFactory(user_id=user.id, uae=uae)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    func = FuncFactory(trip_id=trip.id)
    session.add(func)
    await session.commit()
    await session.refresh(func)

    return func


async def test_update_funcao_success(client, funcao, org_admin_token):
    """Testa atualização de função com sucesso."""
    update_data = {
        'oper': 'op',
        'data_op': '2024-06-15',
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert 'message' in resp
    assert resp['message'] == 'Função atualizada com sucesso'


async def test_update_funcao_change_oper(client, funcao, org_admin_token):
    """Testa alteração da operacionalidade."""
    update_data = {
        'oper': 'ba',
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_change_data_op(client, funcao, org_admin_token):
    """Testa alteração da data de operacionalidade."""
    update_data = {
        'oper': funcao.oper,
        'data_op': '2024-12-31',
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_set_data_op_to_null(
    client, funcao, org_admin_token
):
    """Testa que pode definir data_op como null."""
    update_data = {
        'oper': funcao.oper,
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_not_found(client, org_admin_token):
    """Testa que retorna 404 para função inexistente."""
    update_data = {
        'oper': 'op',
        'data_op': None,
    }

    response = await client.put(
        '/ops/trips/func/99999',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Função não encontrada'


async def test_update_funcao_invalid_oper_fails(
    client, funcao, org_admin_token
):
    """Testa que operacionalidade inválida falha na validação."""
    update_data = {
        'oper': 'invalid',
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_funcao_oper_only_without_data_op(
    client, funcao, org_admin_token
):
    """Testa atualização com oper e sem data_op (None)."""
    update_data = {
        'oper': 'in',
        'data_op': None,
    }

    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_update_funcao_other_org_not_found(
    client, session, org_admin_token
):
    """Função de tripulante de outra UAE é invisível (404)."""
    foreign_func = await _make_foreign_func(session)

    response = await client.put(
        f'/ops/trips/func/{foreign_func.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
        json={'oper': 'op', 'data_op': None},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Função não encontrada'


async def test_update_funcao_missing_active_org_fails(client, funcao, token):
    """Sem org ativa no token, atualizar função responde 400."""
    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'oper': 'op', 'data_op': None},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_funcao_without_token_fails(client, funcao):
    """Sem autenticação, o endpoint responde 401."""
    response = await client.put(
        f'/ops/trips/func/{funcao.id}',
        json={'oper': 'op', 'data_op': None},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_funcao_all_oper_values(
    client, session, trips, org_admin_token
):
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
            headers={'Authorization': f'Bearer {org_admin_token}'},
            json=update_data,
        )

        assert response.status_code == HTTPStatus.OK
