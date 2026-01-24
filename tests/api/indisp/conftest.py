"""
Fixtures específicas para testes do módulo Indisp (Indisponibilidades).

Este conftest.py contém fixtures usadas para testar endpoints relacionados a:
- Criação de indisponibilidades
- Listagem de indisponibilidades por usuário
- Listagem de indisponibilidades por tripulante/função
- Atualização e deleção de indisponibilidades

Fixtures disponíveis:
- indisp: Uma indisponibilidade básica
- indisps: Múltiplas indisponibilidades para testes de listagem
- trip_with_func: Tripulante com função para teste de get_crew_indisp
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.public.tripulantes import Tripulante
from tests.factories import FuncFactory, IndispFactory, TripFactory


@pytest.fixture
async def indisp(session, users):
    """
    Cria uma indisponibilidade básica para testes.

    A indisponibilidade é criada pelo primeiro usuário (user)
    para o segundo usuário (other_user).

    Uso:
        async def test_get_indisp(client, indisp):
            response = await client.get(f'/indisp/user/{indisp.user_id}')
            assert response.status_code == 200

    Returns:
        Indisp: Objeto de indisponibilidade
    """
    user, other_user = users

    indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
    )

    session.add(indisp)
    await session.commit()
    await session.refresh(indisp)

    return indisp


@pytest.fixture
async def indisps(session, users):
    """
    Cria múltiplas indisponibilidades para testes de listagem e filtros.

    Cria 5 indisponibilidades com datas e motivos variados:
    - Alternando entre 'svc' e 'fer' para testar filtro por mtv
    - Datas espaçadas de 10 em 10 dias para testar filtro por data

    Uso:
        async def test_list_indisps(client, users, indisps):
            _, other_user = users
            response = await client.get(f'/indisp/user/{other_user.id}')
            assert len(response.json()) == 5

    Returns:
        list[Indisp]: Lista com 5 indisponibilidades
    """
    user, other_user = users

    db_indisps = []
    for i in range(5):
        indisp = IndispFactory(
            user_id=other_user.id,
            created_by=user.id,
            date_start=date.today() - timedelta(days=i * 10),
            date_end=date.today() - timedelta(days=i * 10 - 5),
            mtv='svc' if i % 2 == 0 else 'fer',
        )
        db_indisps.append(indisp)

    session.add_all(db_indisps)
    await session.commit()

    for instance in db_indisps:
        await session.refresh(instance)

    return db_indisps


@pytest.fixture
async def trip_with_func(session, users):
    """
    Cria tripulante com função para teste de get_crew_indisp.

    O endpoint GET /indisp/ requer tripulantes ativos com funções
    específicas para retornar dados. Esta fixture cria:
    - Um tripulante ativo vinculado ao primeiro usuário
    - Uma função 'pil' vinculada ao tripulante

    Uso:
        async def test_get_crew_indisp(client, trip_with_func):
            trip, func = trip_with_func
            response = await client.get(
                '/indisp/',
                params={'funcao': func.func, 'uae': trip.uae}
            )
            assert response.status_code == 200

    Returns:
        tuple: (trip, func) - Tripulante e função vinculados
    """
    user, _ = users

    trip = TripFactory(user_id=user.id, uae='11gt', active=True)
    session.add(trip)
    await session.commit()

    func = FuncFactory(trip_id=trip.id, func='pil')
    session.add(func)
    await session.commit()
    await session.refresh(func)

    # Recarrega trip com relacionamento funcs para garantir consistência
    trip = await session.scalar(
        select(Tripulante)
        .where(Tripulante.id == trip.id)
        .options(selectinload(Tripulante.funcs))
    )

    return trip, func
