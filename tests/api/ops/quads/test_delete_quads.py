"""
Testes para o endpoint DELETE /ops/quads/{id}.

Este endpoint deleta um quadrinho pelo ID. Requer autenticação.
"""

from datetime import date
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.quads import Quad
from tests.factories import QuadFactory

pytestmark = pytest.mark.anyio


async def test_delete_quad_success(client, session, trip, token):
    """Testa deleção de quadrinho com sucesso."""
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

    response = await client.delete(
        f'/ops/quads/{quad_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {'detail': 'Quadrinho deletado'}

    # Verifica que foi removido do banco
    db_quad = await session.scalar(select(Quad).where(Quad.id == quad_id))
    assert db_quad is None


async def test_delete_quad_not_found(client, token):
    """Testa deleção de quadrinho inexistente."""
    response = await client.delete(
        '/ops/quads/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['detail'] == 'Quad not found'


async def test_delete_quad_invalid_id_format(client, token):
    """Testa deleção com ID inválido."""
    response = await client.delete(
        '/ops/quads/invalid',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_delete_quad_only_deletes_specified(
    client, session, trip, token
):
    """Testa que apenas o quadrinho especificado é deletado."""
    quad1 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 1))
    quad2 = QuadFactory(trip_id=trip.id, type_id=1, value=date(2024, 1, 2))

    session.add_all([quad1, quad2])
    await session.commit()
    await session.refresh(quad1)
    await session.refresh(quad2)

    # Deleta apenas o primeiro
    response = await client.delete(
        f'/ops/quads/{quad1.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    # Verifica que quad1 foi deletado
    db_quad1 = await session.scalar(select(Quad).where(Quad.id == quad1.id))
    assert db_quad1 is None

    # Verifica que quad2 ainda existe
    db_quad2 = await session.scalar(select(Quad).where(Quad.id == quad2.id))
    assert db_quad2 is not None


async def test_delete_quad_from_different_trip(client, session, trips, token):
    """Testa deleção de quadrinho de outro tripulante."""
    trip, other_trip = trips

    quad_other = QuadFactory(
        trip_id=other_trip.id,
        type_id=1,
        value=date.today(),
    )

    session.add(quad_other)
    await session.commit()
    await session.refresh(quad_other)

    # Deleta quadrinho do outro tripulante
    # (O endpoint não verifica ownership, apenas deleta pelo ID)
    response = await client.delete(
        f'/ops/quads/{quad_other.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK


async def test_delete_quad_without_token_fails(client, session, trip):
    """Testa que requisição sem token falha."""
    quad = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    response = await client.delete(f'/ops/quads/{quad.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
