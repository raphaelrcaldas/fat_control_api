from http import HTTPStatus

import pytest

# from sqlalchemy.future import select
# from fcontrol_api.models import Tripulante
from fcontrol_api.schemas.tripulantes import TripSchema, TripWithFuncs

from .factories import TripFactory

pytestmark = pytest.mark.anyio


async def test_create_trip(client, user):
    response = await client.post(
        '/ops/trips/',
        json={
            'user_id': user.id,
            'active': True,
            'uae': '11gt',
            'trig': 'rph',
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        'detail': 'Tripulante adicionado com sucesso',
        'data': {
            'user_id': user.id,
            'trig': 'rph',
            'uae': '11gt',
            'active': True,
        },
    }


async def test_create_trip_error_trig(client, trip):
    new_trip = TripFactory(user_id=trip.user_id)

    response = await client.post(
        '/ops/trips/',
        json={
            'user_id': new_trip.user_id,
            'trig': trip.trig,
            'active': new_trip.active,
            'uae': new_trip.uae,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Trigrama já registrado'}


async def test_create_trip_error_ja_existe(client, trip):
    new_trip = TripFactory(user_id=trip.user_id + 1)

    response = await client.post(
        '/ops/trips/',
        json={
            'user_id': trip.user.id,
            'trig': new_trip.trig,
            'active': new_trip.active,
            'uae': trip.uae,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Tripulante já registrado'}


async def test_get_unique_trip(client, trip):
    trip_schema = TripWithFuncs.model_validate(trip).model_dump()

    response = await client.get(f'/ops/trips/{trip.id}')

    assert response.status_code == HTTPStatus.OK
    assert response.json() == trip_schema


async def test_get_unique_trip_error_not_found(client):
    response = await client.get('/ops/trips/1')

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {'detail': 'Crew member not found'}


async def test_read_list_trips(client, trip):
    trip_schema = TripWithFuncs.model_validate(trip).model_dump()

    response = await client.get(
        '/ops/trips/',
        params={
            'uae': trip.uae,
            'active': trip.active,
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [trip_schema]


async def test_update_trip(client, trip):
    trip_schema = TripSchema.model_validate(trip).model_dump()
    trip_schema['trig'] = 'exe'
    trip_schema['active'] = not trip.active

    response = await client.put(
        f'/ops/trips/{trip.id}',
        json={
            'trig': trip_schema['trig'],
            'active': trip_schema['active'],
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        'detail': 'Tripulante atualizado com sucesso',
        'data': trip_schema,
    }


async def test_update_trip_error_crew_member_not_found(client, trip):
    response = await client.put(
        f'/ops/trips/{trip.id + 1}',
        json={
            'trig': 'tst',
            'active': False,
        },
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {
        'detail': 'Crew member not found',
    }


# async def test_update_trip_error_trig_ja_registrado(client, two_trips):
#     (trip, other_trip) = two_trips

#     print(trip)
#     print(other_trip)

#     response = await client.put(
#         f'/ops/trips/{other_trip.id}',
#         json={
#             'trig': trip.trig,
#             'active': trip.active,
#         }
#     )

#     assert response.status_code == HTTPStatus.BAD_REQUEST
#     assert response.json() == {
#         'detail': 'Trigrama já registrado',
#     }
