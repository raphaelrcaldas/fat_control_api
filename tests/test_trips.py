import random
from http import HTTPStatus

import pytest

from fcontrol_api.schemas.tripulantes import TripSchema, TripWithFuncs

from .factories import TripFactory

pytestmark = pytest.mark.anyio


async def test_create_trip(client, users):
    (user, _) = users

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


async def test_create_trip_error_trig(client, trips):
    (trip, _) = trips

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


async def test_create_trip_error_ja_existe(client, trips):
    (trip, _) = trips

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


async def test_get_unique_trip(client, trips):
    (trip, _) = trips

    trip_schema = TripWithFuncs.model_validate(trip).model_dump()

    response = await client.get(f'/ops/trips/{trip.id}')

    assert response.status_code == HTTPStatus.OK
    assert response.json() == trip_schema


async def test_get_unique_trip_error_not_found(client):
    response = await client.get('/ops/trips/1')

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {'detail': 'Crew member not found'}


async def test_read_list_trips(client, trips):
    (trip, _) = trips

    trips_list = [
        TripWithFuncs.model_validate(trip).model_dump() for trip in trips
    ]

    trips_list = list(
        filter(
            (
                lambda x: (x['uae'] == trip.uae)
                and (x['active'] == trip.active)
            ),
            trips_list,
        )
    )

    response = await client.get(
        '/ops/trips/',
        params={
            'uae': trip.uae,
            'active': trip.active,
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == trips_list


async def test_update_trip(client, trips):
    (trip, _) = trips

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


async def test_update_trip_error_trip_not_found(client, trips):
    def random_id(numeros_excluir):
        numeros_possiveis = list(range(1, 999))
        for numero in numeros_excluir:
            if numero in numeros_possiveis:
                numeros_possiveis.remove(numero)
        return random.choice(numeros_possiveis)

    response = await client.put(
        f'/ops/trips/{random_id([i.id for i in trips])}',
        json={
            'trig': 'tst',
            'active': False,
        },
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {
        'detail': 'Crew member not found',
    }


async def test_update_trip_error_trig_ja_registrado(client, trips):
    (trip, other_trip) = trips

    response = await client.put(
        f'/ops/trips/{other_trip.id}',
        json={
            'trig': trip.trig,
            'active': trip.active,
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'Trigrama já registrado',
    }
