from http import HTTPStatus

from fcontrol_api.schemas.tripulantes import TripSchema, TripWithFuncs

from .factories import TripFactory


def test_create_trip(client, user):
    r_trip = client.post(
        'ops/trips/',
        json={
            'user_id': user.id,
            'trig': 'rph',
            'active': True,
            'uae': '11gt',
        },
    )

    assert r_trip.status_code == HTTPStatus.CREATED
    assert r_trip.json() == {
        'detail': 'Tripulante adicionado com sucesso',
        'data': {
            'user_id': user.id,
            'trig': 'rph',
            'uae': '11gt',
            'active': True,
        },
    }


def test_create_trip_error_trig(client, trip, other_user):
    new_trip = TripFactory(user_id=other_user.id)

    r_trip = client.post(
        'ops/trips/',
        json={
            'user_id': new_trip.user_id,
            'trig': trip.trig,
            'active': new_trip.active,
            'uae': new_trip.uae,
        },
    )

    assert r_trip.status_code == HTTPStatus.BAD_REQUEST
    assert r_trip.json() == {'detail': 'Trigrama já registrado'}


def test_create_trip_error_ja_existe(client, trip, other_user):
    new_trip = TripFactory(user_id=other_user.id)

    r_trip = client.post(
        'ops/trips/',
        json={
            'user_id': trip.user.id,
            'trig': new_trip.trig,
            'active': new_trip.active,
            'uae': trip.uae,
        },
    )

    assert r_trip.status_code == HTTPStatus.BAD_REQUEST
    assert r_trip.json() == {'detail': 'Tripulante já registrado'}


def test_get_unique_trip(client, trip):
    trip_schema = TripWithFuncs.model_validate(trip).model_dump()

    r_trip = client.get(f'ops/trips/{trip.id}')

    assert r_trip.status_code == HTTPStatus.OK
    assert r_trip.json() == trip_schema


def test_get_unique_trip_error_not_found(client, trip):
    r_trip = client.get(f'ops/trips/{trip.id + 1}')

    assert r_trip.status_code == HTTPStatus.NOT_FOUND
    assert r_trip.json() == {'detail': 'Crew member not found'}


def test_read_list_trips(client, trip):
    trip_schema = TripWithFuncs.model_validate(trip).model_dump()

    r_trip = client.get(
        'ops/trips/',
        params={
            'uae': trip.uae,
            'active': trip.active,
        },
    )

    assert r_trip.status_code == HTTPStatus.OK
    assert r_trip.json() == [trip_schema]


def test_update_trip(client, trip):
    trip_schema = TripSchema.model_validate(trip).model_dump()
    trip_schema['trig'] = 'exe'
    trip_schema['active'] = not trip.active

    r_trip = client.put(
        f'ops/trips/{trip.id}',
        json={
            'trig': trip_schema['trig'],
            'active': trip_schema['active'],
        },
    )

    assert r_trip.status_code == HTTPStatus.OK
    assert r_trip.json() == {
        'detail': 'Tripulante atualizado com sucesso',
        'data': trip_schema,
    }


def test_update_trip_error_trig_ja_resgistrado(client, trip, other_trip):
    r_trip = client.put(
        f'ops/trips/{trip.id}',
        json={
            'trig': other_trip.trig,
            'active': trip.active,
        },
    )

    assert r_trip.status_code == HTTPStatus.BAD_REQUEST
    assert r_trip.json() == {
        'detail': 'Trigrama já registrado',
    }


def test_update_trip_error_crew_member_not_found(client, trip):
    r_trip = client.put(
        f'ops/trips/{trip.id + 1}',
        json={
            'trig': 'tst',
            'active': False,
        },
    )

    assert r_trip.status_code == HTTPStatus.NOT_FOUND
    assert r_trip.json() == {
        'detail': 'Crew member not found',
    }
