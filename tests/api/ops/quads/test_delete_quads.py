"""
Testes para o endpoint DELETE /ops/quads/ (deleção em lote).

Este endpoint recebe uma lista de IDs no corpo (QuadBatchDelete) e remove
os quadrinhos correspondentes. Requer autenticação. Quando nenhum ID
corresponde a um quadrinho existente, responde 404.
"""

from datetime import date
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.shared.quads import Quad
from tests.factories import QuadFactory

pytestmark = pytest.mark.anyio


async def test_delete_quads_success(client, session, trip, token):
    """Testa deleção em lote de um quadrinho com sucesso."""
    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date.today(),
        description='Para deletar',
    )

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    quad_id = quad.id

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [quad_id]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['message'] == '1 quadrinho(s) deletado(s)'

    # Verifica que foi removido do banco
    db_quad = await session.scalar(select(Quad).where(Quad.id == quad_id))
    assert db_quad is None


async def test_delete_quads_multiple(client, session, trip, token):
    """Testa deleção em lote de múltiplos quadrinhos."""
    quad1 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 1))
    quad2 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 2))

    session.add_all([quad1, quad2])
    await session.commit()
    await session.refresh(quad1)
    await session.refresh(quad2)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [quad1.id, quad2.id]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == '2 quadrinho(s) deletado(s)'

    remaining = await session.scalars(
        select(Quad).where(Quad.id.in_([quad1.id, quad2.id]))
    )
    assert remaining.all() == []


async def test_delete_quads_not_found(client, token):
    """Testa que IDs inexistentes retornam 404."""
    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [999999]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert resp['message'] == 'Nenhum quadrinho encontrado'


async def test_delete_quads_partial_match(client, session, trip, token):
    """Testa que IDs mistos removem apenas os existentes (rowcount > 0)."""
    quad = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [quad.id, 999999]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == '1 quadrinho(s) deletado(s)'

    db_quad = await session.scalar(select(Quad).where(Quad.id == quad.id))
    assert db_quad is None


async def test_delete_quads_invalid_id_format(client, token):
    """Testa que IDs em formato inválido falham na validação."""
    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': ['invalid']},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_delete_quads_only_deletes_specified(
    client, session, trip, token
):
    """Testa que apenas os quadrinhos informados são deletados."""
    quad1 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 1))
    quad2 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 2))

    session.add_all([quad1, quad2])
    await session.commit()
    await session.refresh(quad1)
    await session.refresh(quad2)

    # Deleta apenas o primeiro
    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [quad1.id]},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    db_quad1 = await session.scalar(select(Quad).where(Quad.id == quad1.id))
    assert db_quad1 is None

    db_quad2 = await session.scalar(select(Quad).where(Quad.id == quad2.id))
    assert db_quad2 is not None


async def test_delete_quads_from_different_trip(
    client, session, trips, token
):
    """Testa deleção de quadrinho de outro tripulante.

    O endpoint não verifica ownership, apenas deleta pelos IDs informados.
    """
    _, other_trip = trips

    quad_other = QuadFactory(
        trip_id=other_trip.id,
        type_id=1,
        value=date.today(),
    )

    session.add(quad_other)
    await session.commit()
    await session.refresh(quad_other)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [quad_other.id]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK


async def test_delete_quads_without_token_fails(client, session, trip):
    """Testa que requisição sem token falha."""
    quad = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [quad.id]},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
