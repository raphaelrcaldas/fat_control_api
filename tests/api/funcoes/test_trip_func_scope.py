"""Write-path de tripulante: a função tem de ser operada pela unidade.

Antes a validação era um Literal fechado no schema, igual para todo mundo.
Agora o conjunto é dado (`funcoes_uae`) e depende da org ativa.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import delete

from fcontrol_api.models.shared.funcoes import FuncaoUae
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio


def _auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def sem_comissario(session):
    """Tira 'tf' das funções operadas pela org de teste."""
    await session.execute(
        delete(FuncaoUae).where(
            FuncaoUae.uae == '11gt', FuncaoUae.func_cod == 'tf'
        )
    )
    await session.commit()
    yield
    session.add(FuncaoUae(uae='11gt', func_cod='tf'))
    await session.commit()


async def test_create_trip_recusa_funcao_nao_operada(
    client, session, token, sem_comissario
):
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    response = await client.post(
        '/ops/trips/',
        headers=_auth(token),
        json={
            'user_id': user.id,
            'trig': 'qwe',
            'active': True,
            'func': 'tf',
            'oper': 'op',
            'proj': 'kc-390',
            'data_op': '2020-01-15',
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()['message'] == 'Função não operada pela organização'


async def test_create_trip_aceita_funcao_operada(client, session, token):
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    response = await client.post(
        '/ops/trips/',
        headers=_auth(token),
        json={
            'user_id': user.id,
            'trig': 'rty',
            'active': True,
            'func': 'tf',
            'oper': 'op',
            'proj': 'kc-390',
            'data_op': '2020-01-15',
        },
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_patch_trip_recusa_funcao_nao_operada(
    client, session, token, sem_comissario
):
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip = TripFactory(user_id=user.id, uae='11gt', active=True, func='pil')
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    response = await client.patch(
        f'/ops/trips/{trip.id}',
        headers=_auth(token),
        json={'func': 'tf'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_set_quads_type_funcs_recusa_funcao_nao_operada(
    client, token, sem_comissario
):
    response = await client.put(
        '/ops/quads/types/1/funcs',
        headers=_auth(token),
        json={'funcs': ['pil', 'tf']},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'tf' in response.json()['message']
