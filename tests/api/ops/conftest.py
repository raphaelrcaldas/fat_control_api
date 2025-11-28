"""
Fixtures específicas para testes do módulo OPS (Operações).

Este conftest.py contém fixtures usadas para testar endpoints relacionados a:
- Tripulantes (trips)
- Funções (funcoes)
- Quadrantes (quads)

Fixtures disponíveis:
- trips: Tupla com dois tripulantes (user e other_user)
- trip: Um único tripulante (primeiro da tupla trips)
- funcao: Uma função vinculada a um tripulante
- quad: Um quadrante vinculado a um tripulante
"""

import pytest

from tests.factories import FuncFactory, QuadFactory, TripFactory


@pytest.fixture
async def trips(session, users):
    """
    Cria dois tripulantes no banco de dados,
    associados aos usuários da fixture 'users'.

    Esta fixture é útil para testar operações que
    envolvem múltiplos tripulantes,
    como listagens, comparações, e operações de autorização.

    Uso:
        async def test_list_trips(client, trips):
            trip, other_trip = trips
            response = await client.get('/ops/trips')
            assert len(response.json()) >= 2

    Returns:
        tuple: (trip, other_trip) - Dois objetos Tripulante
    """
    (user, other_user) = users

    trip = TripFactory(user_id=user.id)
    other_trip = TripFactory(user_id=other_user.id)

    db_trips = [trip, other_trip]

    session.add_all(db_trips)
    await session.commit()

    for instance in db_trips:
        await session.refresh(instance)

    return (trip, other_trip)


@pytest.fixture
async def trip(trips):
    """
    Retorna o primeiro tripulante da fixture 'trips'.

    Fixture de conveniência para testes que precisam de apenas um tripulante.
    Automaticamente depende de 'trips', garantindo que sempre há pelo menos
    dois tripulantes no banco para testes que precisem dessa premissa.

    Uso:
        async def test_get_trip(client, trip):
            response = await client.get(f'/ops/trips/{trip.id}')
            assert response.status_code == 200

    Returns:
        Tripulante: Primeiro tripulante da fixture trips
    """
    return trips[0]


@pytest.fixture
async def funcao(session, trip):
    """
    Cria uma função vinculada a um tripulante.

    Funções representam atividades, operações ou projetos que um tripulante
    está executando. Esta fixture é útil para testar CRUD de funções e
    relacionamentos trip -> funções.

    Uso:
        async def test_create_funcao(client, trip, funcao):
            assert funcao.trip_id == trip.id
            response = await client.get(f'/ops/funcoes/{funcao.id}')
            assert response.status_code == 200

    Returns:
        Funcao: Objeto de função vinculado ao tripulante
    """
    func = FuncFactory(trip_id=trip.id)

    session.add(func)
    await session.commit()
    await session.refresh(func)

    return func


@pytest.fixture
async def quad(session, trip):
    """
    Cria um quadrante (quad) vinculado a um tripulante.

    Quadrantes representam informações estruturadas associadas a tripulantes,
    como dados de quadros, métricas ou categorias operacionais.

    Uso:
        async def test_create_quad(client, trip, quad):
            assert quad.trip_id == trip.id
            response = await client.get(f'/ops/quads/{quad.id}')
            assert response.status_code == 200

    Returns:
        Quad: Objeto de quadrante vinculado ao tripulante
    """
    quad = QuadFactory(trip_id=trip.id)

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    return quad
