"""
Testes para o endpoint DELETE /ops/trips/func/{id}.

Este endpoint deleta uma função existente.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.funcoes import Funcao
from tests.factories import FuncFactory

pytestmark = pytest.mark.anyio


async def test_delete_funcao_success(client, funcao, token):
    """Testa deleção de função com sucesso."""
    response = await client.delete(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert 'detail' in data
    assert data['detail'] == 'Função deletada'


async def test_delete_funcao_not_found(client, token):
    """Testa que retorna 404 para função inexistente."""
    response = await client.delete(
        '/ops/trips/func/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    data = response.json()
    assert data['detail'] == 'Função não encontrada'


async def test_delete_funcao_removes_from_database(
    client, session, trip, token
):
    """Testa que a função é realmente removida do banco."""
    # Cria uma função
    func = FuncFactory(trip_id=trip.id)
    session.add(func)
    await session.commit()
    await session.refresh(func)
    func_id = func.id

    # Verifica que existe
    db_func = await session.scalar(select(Funcao).where(Funcao.id == func_id))
    assert db_func is not None

    # Deleta
    response = await client.delete(
        f'/ops/trips/func/{func_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que foi removida
    session.expire_all()
    db_func = await session.scalar(select(Funcao).where(Funcao.id == func_id))
    assert db_func is None


async def test_delete_funcao_does_not_affect_other_funcs(
    client, session, trip, token
):
    """Testa que deletar uma função não afeta outras."""
    # Cria duas funções
    func1 = FuncFactory(trip_id=trip.id, func='pil')
    func2 = FuncFactory(trip_id=trip.id, func='mc')
    session.add_all([func1, func2])
    await session.commit()
    await session.refresh(func1)
    await session.refresh(func2)

    # Salva os IDs antes de qualquer operação
    func1_id = func1.id
    func2_id = func2.id

    # Deleta apenas a primeira
    response = await client.delete(
        f'/ops/trips/func/{func1_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Segunda função ainda deve existir
    session.expire_all()
    db_func2 = await session.scalar(
        select(Funcao).where(Funcao.id == func2_id)
    )
    assert db_func2 is not None
    assert db_func2.func == 'mc'


async def test_delete_same_funcao_twice_fails(client, session, trip, token):
    """Testa que deletar a mesma função duas vezes falha na segunda."""
    # Cria uma função
    func = FuncFactory(trip_id=trip.id)
    session.add(func)
    await session.commit()
    await session.refresh(func)
    func_id = func.id

    # Primeira deleção - sucesso
    response = await client.delete(
        f'/ops/trips/func/{func_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    # Segunda deleção - deve falhar
    response = await client.delete(
        f'/ops/trips/func/{func_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
