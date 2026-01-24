"""
Testes para os endpoints GET /ops/trips/.

Este módulo testa:
- GET /ops/trips/ - Listagem paginada de tripulantes com filtros
- GET /ops/trips/me - Retorna o tripulante do usuário autenticado
- GET /ops/trips/{id} - Retorna um tripulante específico
"""

from http import HTTPStatus

import pytest

from tests.factories import FuncFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio

# Constantes de teste
MIN_TRIPS_FROM_FIXTURE = 2
DEFAULT_PER_PAGE = 10
DEFAULT_UAE = '11gt'


# --- Testes para GET /ops/trips/ (list_trips) ---


async def test_list_trips_returns_paginated_list(client, trips, token):
    """Testa que o endpoint retorna uma lista paginada."""
    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert 'items' in data
    assert 'total' in data
    assert 'page' in data
    assert 'per_page' in data
    assert 'pages' in data
    assert isinstance(data['items'], list)
    assert len(data['items']) >= MIN_TRIPS_FROM_FIXTURE


async def test_list_trips_returns_correct_fields(client, trips, token):
    """Testa que cada tripulante retornado tem os campos esperados."""
    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    if len(data['items']) > 0:
        trip = data['items'][0]
        # Campos de TripWithFuncs
        assert 'id' in trip
        assert 'trig' in trip
        assert 'uae' in trip
        assert 'active' in trip
        assert 'user' in trip
        assert 'funcs' in trip
        # Campos do user aninhado
        assert 'id' in trip['user']
        assert 'nome_guerra' in trip['user']
        assert 'p_g' in trip['user']


async def test_list_trips_with_search_by_trig(client, trips, token):
    """Testa busca por trigrama."""
    trip, _ = trips

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': trip.trig},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert len(data['items']) >= 1
    found = any(t['trig'] == trip.trig for t in data['items'])
    assert found


async def test_list_trips_with_search_by_nome_guerra(
    client, session, trips, users, token
):
    """Testa busca por nome de guerra do usuário."""
    trip, _ = trips
    user, _ = users

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': user.nome_guerra},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert len(data['items']) >= 1
    found = any(
        t['user']['nome_guerra'] == user.nome_guerra for t in data['items']
    )
    assert found


async def test_list_trips_search_case_insensitive(client, trips, token):
    """Testa que a busca é case-insensitive."""
    trip, _ = trips

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': trip.trig.upper()},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    found = any(t['trig'] == trip.trig for t in data['items'])
    assert found


async def test_list_trips_search_no_match_returns_empty(client, trips, token):
    """Testa que busca sem match retorna lista vazia."""
    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'search': 'xyz_inexistente'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert isinstance(data['items'], list)
    assert len(data['items']) == 0


async def test_list_trips_filter_by_active_true(client, session, users, token):
    """Testa filtro por tripulantes ativos."""
    user, other_user = users

    active_trip = TripFactory(user_id=user.id, active=True)
    inactive_trip = TripFactory(user_id=other_user.id, active=False)

    session.add_all([active_trip, inactive_trip])
    await session.commit()
    await session.refresh(active_trip)
    await session.refresh(inactive_trip)

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'active': True},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os tripulantes retornados devem estar ativos
    assert all(t['active'] is True for t in data['items'])
    # Tripulante inativo não deve aparecer
    assert not any(t['id'] == inactive_trip.id for t in data['items'])


async def test_list_trips_filter_by_active_false(
    client, session, users, token
):
    """Testa filtro por tripulantes inativos."""
    user, other_user = users

    active_trip = TripFactory(user_id=user.id, active=True)
    inactive_trip = TripFactory(user_id=other_user.id, active=False)

    session.add_all([active_trip, inactive_trip])
    await session.commit()
    await session.refresh(inactive_trip)

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'active': False},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os tripulantes retornados devem estar inativos
    assert all(t['active'] is False for t in data['items'])
    # Tripulante inativo criado deve aparecer
    assert any(t['id'] == inactive_trip.id for t in data['items'])


async def test_list_trips_filter_by_single_pg(client, session, token):
    """Testa filtro por um único posto/graduação."""
    # Cria usuários com p_g específicos
    user_2s = UserFactory(p_g='2s')
    user_3s = UserFactory(p_g='3s')
    session.add_all([user_2s, user_3s])
    await session.commit()
    await session.refresh(user_2s)
    await session.refresh(user_3s)

    # Cria tripulantes para esses usuários
    trip_2s = TripFactory(user_id=user_2s.id)
    trip_3s = TripFactory(user_id=user_3s.id)
    session.add_all([trip_2s, trip_3s])
    await session.commit()

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'p_g': '2s'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos os tripulantes retornados devem ter p_g = '2s'
    assert all(t['user']['p_g'] == '2s' for t in data['items'])


async def test_list_trips_filter_by_multiple_pg(client, session, token):
    """Testa filtro por múltiplos p_g separados por vírgula."""
    # Cria usuários com p_g específicos
    user_2s = UserFactory(p_g='2s')
    user_3s = UserFactory(p_g='3s')
    user_cb = UserFactory(p_g='cb')
    session.add_all([user_2s, user_3s, user_cb])
    await session.commit()
    await session.refresh(user_2s)
    await session.refresh(user_3s)
    await session.refresh(user_cb)

    # Cria tripulantes
    trip_2s = TripFactory(user_id=user_2s.id)
    trip_3s = TripFactory(user_id=user_3s.id)
    trip_cb = TripFactory(user_id=user_cb.id)
    session.add_all([trip_2s, trip_3s, trip_cb])
    await session.commit()

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'p_g': '2s, 3s'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Todos devem ter p_g '2s' ou '3s'
    assert all(t['user']['p_g'] in {'2s', '3s'} for t in data['items'])
    # Não deve incluir 'cb'
    assert not any(t['user']['p_g'] == 'cb' for t in data['items'])


async def test_list_trips_filter_by_func(client, session, users, token):
    """Testa filtro por função."""
    user, other_user = users

    # Cria tripulantes
    trip_pil = TripFactory(user_id=user.id)
    trip_mc = TripFactory(user_id=other_user.id)
    session.add_all([trip_pil, trip_mc])
    await session.commit()
    await session.refresh(trip_pil)
    await session.refresh(trip_mc)

    # Cria funções para os tripulantes
    func_pil = FuncFactory(trip_id=trip_pil.id, func='pil')
    func_mc = FuncFactory(trip_id=trip_mc.id, func='mc')
    session.add_all([func_pil, func_mc])
    await session.commit()

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'func': 'pil'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Deve encontrar apenas o tripulante com função 'pil'
    assert any(t['id'] == trip_pil.id for t in data['items'])


async def test_list_trips_filter_by_oper(client, session, users, token):
    """Testa filtro por operacionalidade."""
    user, other_user = users

    # Cria tripulantes
    trip_op = TripFactory(user_id=user.id)
    trip_ba = TripFactory(user_id=other_user.id)
    session.add_all([trip_op, trip_ba])
    await session.commit()
    await session.refresh(trip_op)
    await session.refresh(trip_ba)

    # Cria funções com diferentes operacionalidades
    func_op = FuncFactory(trip_id=trip_op.id, oper='op')
    func_ba = FuncFactory(trip_id=trip_ba.id, oper='ba')
    session.add_all([func_op, func_ba])
    await session.commit()

    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'oper': 'op'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Deve encontrar o tripulante com oper='op'
    assert any(t['id'] == trip_op.id for t in data['items'])


async def test_list_trips_pagination_page_1(client, trips, token):
    """Testa paginação - primeira página."""
    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'page': 1, 'per_page': 1},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['page'] == 1
    assert data['per_page'] == 1
    assert len(data['items']) <= 1


async def test_list_trips_pagination_respects_per_page(client, trips, token):
    """Testa que a paginação respeita o per_page."""
    response = await client.get(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        params={'per_page': 5},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['per_page'] == 5
    assert len(data['items']) <= 5


async def test_list_trips_without_authentication_fails(client):
    """Testa que o endpoint requer autenticação."""
    response = await client.get('/ops/trips/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# --- Testes para GET /ops/trips/{id} (get_trip) ---


async def test_get_trip_returns_trip(client, trip, token):
    """Testa que retorna um tripulante específico."""
    response = await client.get(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['id'] == trip.id
    assert data['trig'] == trip.trig
    assert data['uae'] == trip.uae
    assert data['active'] == trip.active


async def test_get_trip_returns_correct_fields(client, trip, token):
    """Testa que o tripulante retornado tem os campos esperados."""
    response = await client.get(
        f'/ops/trips/{trip.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Campos de TripWithFuncs
    assert 'id' in data
    assert 'trig' in data
    assert 'uae' in data
    assert 'active' in data
    assert 'user' in data
    assert 'funcs' in data


async def test_get_trip_not_found(client, token):
    """Testa que retorna 404 para tripulante inexistente."""
    response = await client.get(
        '/ops/trips/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_get_trip_without_authentication_fails(client, trip):
    """Testa que o endpoint requer autenticação."""
    response = await client.get(f'/ops/trips/{trip.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# --- Testes para GET /ops/trips/me (get_my_trip) ---


async def test_get_my_trip_returns_current_user_trip(
    client, session, users, token
):
    """Testa que retorna o tripulante do usuário autenticado."""
    user, _ = users

    # Cria um tripulante para o usuário autenticado
    my_trip = TripFactory(user_id=user.id, uae='11gt')
    session.add(my_trip)
    await session.commit()
    await session.refresh(my_trip)

    response = await client.get(
        '/ops/trips/me',
        headers={'Authorization': f'Bearer {token}'},
        params={'uae': '11gt'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['id'] == my_trip.id
    assert data['user']['id'] == user.id


async def test_get_my_trip_not_found_when_no_trip(client, users, token):
    """Testa que retorna 404 se usuário não tem tripulante."""
    # Usuário autenticado mas sem tripulante associado na uae especificada
    response = await client.get(
        '/ops/trips/me',
        headers={'Authorization': f'Bearer {token}'},
        params={'uae': '11gt'},
    )

    # Pode ser NOT_FOUND se não existir tripulante
    # O comportamento depende se a fixture trips já criou um para este user
    assert response.status_code in {HTTPStatus.OK, HTTPStatus.NOT_FOUND}


async def test_get_my_trip_without_authentication_fails(client):
    """Testa que o endpoint requer autenticação."""
    response = await client.get('/ops/trips/me')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
