"""
Testes para o endpoint GET /indisp/.

Este endpoint retorna indisponibilidades de tripulantes filtrados por
função (funcao) e unidade aérea (uae).
Requer autenticação (middleware global).
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import FuncFactory, IndispFactory, TripFactory

pytestmark = pytest.mark.anyio


async def test_get_crew_indisp_success(
    client, session, users, trip_with_func, token
):
    """Testa listagem de indisponibilidades de tripulantes com sucesso."""
    user, _ = users
    trip, func = trip_with_func

    # Cria uma indisp para o tripulante
    indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
    )
    session.add(indisp)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1
    assert data[0]['trip']['id'] == trip.id


async def test_get_crew_indisp_response_structure(
    client, session, users, trip_with_func, token
):
    """Testa estrutura correta da resposta (trip, indisps)."""
    user, _ = users
    trip, func = trip_with_func

    indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
    )
    session.add(indisp)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert 'trip' in item
    assert 'indisps' in item

    # Estrutura do trip
    trip_data = item['trip']
    assert 'id' in trip_data
    assert 'trig' in trip_data
    assert 'user' in trip_data
    assert 'func' in trip_data

    # Estrutura do user dentro do trip
    user_data = trip_data['user']
    assert 'id' in user_data
    assert 'nome_guerra' in user_data


async def test_get_crew_indisp_no_trips_returns_empty(client, token):
    """Testa que sem tripulantes retorna lista vazia."""
    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil', 'uae': '11gt'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


async def test_get_crew_indisp_excludes_inactive_users(
    client, session, users, token
):
    """Testa que usuários inativos não são retornados."""
    user, other_user = users

    # Cria trip para o user inativo
    other_user.active = False
    await session.commit()

    trip = TripFactory(user_id=other_user.id, uae='11gt', active=True)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    func = FuncFactory(trip_id=trip.id, func='pil')
    session.add(func)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil', 'uae': '11gt'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


async def test_get_crew_indisp_excludes_inactive_trips(
    client, session, users, token
):
    """Testa que tripulantes inativos não são retornados."""
    user, _ = users

    trip = TripFactory(user_id=user.id, uae='11gt', active=False)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    func = FuncFactory(trip_id=trip.id, func='pil')
    session.add(func)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil', 'uae': '11gt'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


async def test_get_crew_indisp_filters_old_indisps(
    client, session, users, trip_with_func, token
):
    """Testa que indisps com mais de 30 dias são filtradas."""
    user, _ = users
    trip, func = trip_with_func

    # Indisp antiga (mais de 30 dias)
    old_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=60),
        date_end=date.today() - timedelta(days=35),
    )
    # Indisp recente
    new_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=10),
        date_end=date.today() + timedelta(days=5),
    )

    session.add_all([old_indisp, new_indisp])
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1

    indisps = data[0]['indisps']
    assert len(indisps) == 1
    # Verifica que apenas a indisp recente foi retornada
    indisp_ids = [i['id'] for i in indisps]
    assert new_indisp.id in indisp_ids
    assert old_indisp.id not in indisp_ids


async def test_get_crew_indisp_trip_without_indisps(
    client, session, users, trip_with_func, token
):
    """Testa que tripulante sem indisps retorna lista vazia de indisps."""
    trip, func = trip_with_func

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1
    assert data[0]['indisps'] == []


async def test_get_crew_indisp_groups_indisps_by_user(
    client, session, users, trip_with_func, token
):
    """Testa que múltiplas indisps de um usuário são agrupadas."""
    user, _ = users
    trip, func = trip_with_func

    # Cria múltiplas indisps para o mesmo usuário
    indisp1 = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    indisp2 = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() + timedelta(days=10),
        date_end=date.today() + timedelta(days=15),
        mtv='svc',
    )

    session.add_all([indisp1, indisp2])
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1  # Apenas um tripulante

    indisps = data[0]['indisps']
    assert len(indisps) == 2  # Duas indisps agrupadas


async def test_get_crew_indisp_indisps_ordered_by_date_end_desc(
    client, session, users, trip_with_func, token
):
    """Testa que indisps são ordenadas por date_end desc dentro do grupo."""
    user, _ = users
    trip, func = trip_with_func

    old_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=10),
        date_end=date.today() - timedelta(days=5),
    )
    new_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
    )

    session.add_all([old_indisp, new_indisp])
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    indisps = data[0]['indisps']
    # Mais recente primeiro
    assert indisps[0]['id'] == new_indisp.id
    assert indisps[1]['id'] == old_indisp.id


async def test_get_crew_indisp_filters_by_funcao(
    client, session, users, token
):
    """Testa que filtro por funcao funciona corretamente."""
    user, other_user = users

    # Tripulante com função 'pil'
    trip_pil = TripFactory(user_id=user.id, uae='11gt', active=True)
    session.add(trip_pil)
    await session.commit()
    await session.refresh(trip_pil)

    func_pil = FuncFactory(trip_id=trip_pil.id, func='pil')
    session.add(func_pil)
    await session.commit()

    # Tripulante com função 'nav'
    trip_nav = TripFactory(user_id=other_user.id, uae='11gt', active=True)
    session.add(trip_nav)
    await session.commit()
    await session.refresh(trip_nav)

    func_nav = FuncFactory(trip_id=trip_nav.id, func='nav')
    session.add(func_nav)
    await session.commit()

    # Busca apenas pilotos
    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil', 'uae': '11gt'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1
    assert data[0]['trip']['id'] == trip_pil.id


async def test_get_crew_indisp_filters_by_uae(client, session, users, token):
    """Testa que filtro por uae funciona corretamente."""
    user, other_user = users

    # Tripulante na UAE '11gt'
    trip_11gt = TripFactory(user_id=user.id, uae='11gt', active=True)
    session.add(trip_11gt)
    await session.commit()
    await session.refresh(trip_11gt)

    func_11gt = FuncFactory(trip_id=trip_11gt.id, func='pil')
    session.add(func_11gt)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil', 'uae': '11gt'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1
    assert data[0]['trip']['id'] == trip_11gt.id


async def test_get_crew_indisp_func_in_response(
    client, session, users, trip_with_func, token
):
    """Testa que a função é incluída na resposta."""
    trip, func = trip_with_func

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func, 'uae': trip.uae},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) == 1

    func_data = data[0]['trip']['func']
    assert func_data is not None
    assert func_data['func'] == func.func


async def test_get_crew_indisp_without_token_fails(client):
    """Testa que requisição sem token falha."""
    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil', 'uae': '11gt'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
