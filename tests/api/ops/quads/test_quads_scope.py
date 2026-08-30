"""Isolamento cross-org de quadrinhos (/quads).

Quads penduram num tripulante (escopo `Tripulante.uae`). A limpeza de
órfãos só remove quads de tripulantes inativos DA org ativa.
"""

from datetime import date
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.models.shared.quads import Quad, QuadsGroup, QuadsType
from tests.factories import QuadFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio

ORFAOS_URL = '/ops/quads/orfaos'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def _mk_trip(session, *, uae, active):
    user = UserFactory(unidade=uae)
    user.active = active
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae=uae, active=active)
    session.add(trip)
    await session.flush()
    return trip


async def test_orfaos_delete_nao_remove_de_outra_org(client, session, token):
    """Admin da '11gt' não apaga quad órfão de tripulante inativo da '1gt'."""
    trip1 = await _mk_trip(session, uae='1gt', active=False)
    quad = QuadFactory(trip_id=trip1.id)
    session.add(quad)
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'trip_ids': [trip1.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK

    # O quad da '1gt' continua no banco.
    still = await session.get(Quad, quad.id)
    assert still is not None


async def test_orfaos_delete_da_propria_org_remove(
    client, session, admin_1gt_token
):
    """Controle positivo: admin da '1gt' remove o próprio quad órfão."""
    trip1 = await _mk_trip(session, uae='1gt', active=False)
    quad = QuadFactory(trip_id=trip1.id)
    session.add(quad)
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'trip_ids': [trip1.id]},
        headers=_auth(admin_1gt_token),
    )
    assert resp.status_code == HTTPStatus.OK

    session.expire_all()
    gone = await session.get(Quad, quad.id)
    assert gone is None


async def test_create_recusa_tipo_de_outra_org(client, session, trip, token):
    """`type_id` também é multi-tenant: `quads_type` pende de `quads_group`.

    Sem esta amarra o gestor da '11gt' gravava quadrinho com tipo da
    '1gt' — e, desde as notificações, o RÓTULO desse tipo passava a ser
    persistido no payload entregue ao tripulante.
    """
    grupo_1gt = QuadsGroup(short='alheio', long='grupo da 1gt', uae='1gt')
    session.add(grupo_1gt)
    await session.flush()
    tipo_1gt = QuadsType(group_id=grupo_1gt.id, short='alh', long='alheio')
    session.add(tipo_1gt)
    await session.commit()
    await session.refresh(tipo_1gt)

    response = await client.post(
        '/ops/quads/',
        json=[
            {
                'value': date.today().isoformat(),
                'type_id': tipo_1gt.id,
                'description': 'tipo de outra org',
                'trip_id': trip.id,
            }
        ],
        headers=_auth(token),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tipo de quadrinho não encontrado'

    gravado = await session.scalar(
        select(Quad).where(Quad.type_id == tipo_1gt.id)
    )
    assert gravado is None

    notificado = await session.scalar(
        select(Notificacao).where(Notificacao.recurso == 'ops.quadro')
    )
    assert notificado is None
