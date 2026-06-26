"""
Testes para o endpoint DELETE /ops/trips/func/{id}.

Este endpoint deleta uma função existente.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.shared.funcoes import Funcao
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


async def test_delete_funcao_success(client, funcao, org_admin_token):
    """Testa deleção de função com sucesso."""
    response = await client.delete(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    assert resp['status'] == 'success'
    assert 'message' in resp
    assert resp['message'] == 'Função deletada'


async def test_delete_funcao_not_found(client, org_admin_token):
    """Testa que retorna 404 para função inexistente."""
    response = await client.delete(
        '/ops/trips/func/99999',
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Função não encontrada'


async def test_delete_funcao_removes_from_database(
    client, session, trip, org_admin_token
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
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que foi removida
    session.expire_all()
    db_func = await session.scalar(select(Funcao).where(Funcao.id == func_id))
    assert db_func is None


async def test_delete_funcao_does_not_affect_other_funcs(
    client, session, trip, org_admin_token
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
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Segunda função ainda deve existir
    session.expire_all()
    db_func2 = await session.scalar(
        select(Funcao).where(Funcao.id == func2_id)
    )
    assert db_func2 is not None
    assert db_func2.func == 'mc'


async def test_delete_funcao_other_org_not_found(
    client, session, org_admin_token
):
    """Função de tripulante de outra UAE é invisível (404)."""
    foreign_func = await _make_foreign_func(session)
    foreign_id = foreign_func.id

    response = await client.delete(
        f'/ops/trips/func/{foreign_id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Função não encontrada'

    # A função da outra UAE permanece intacta
    session.expire_all()
    db_func = await session.scalar(
        select(Funcao).where(Funcao.id == foreign_id)
    )
    assert db_func is not None


async def test_delete_funcao_missing_active_org_fails(client, funcao, token):
    """Sem org ativa no token, deletar função responde 400."""
    response = await client.delete(
        f'/ops/trips/func/{funcao.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_delete_funcao_without_token_fails(client, funcao):
    """Sem autenticação, o endpoint responde 401."""
    response = await client.delete(f'/ops/trips/func/{funcao.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_delete_same_funcao_twice_fails(
    client, session, trip, org_admin_token
):
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
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )
    assert response.status_code == HTTPStatus.OK

    # Segunda deleção - deve falhar
    response = await client.delete(
        f'/ops/trips/func/{func_id}',
        headers={'Authorization': f'Bearer {org_admin_token}'},
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
