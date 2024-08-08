from http import HTTPStatus

from tests.factories import TripFactory, UserFactory


def test_create_trip(client, session):
    user = UserFactory()
    trip = TripFactory(user_id=1)

    session.add(user)
    session.commit()
    session.refresh(user)

    r_trip = client.post(
        '/trips/',
        json={
            'trig': trip.trig,
            'func': trip.func,
            'user_id': trip.user_id,
            'oper': trip.oper,
        },
    )

    assert r_trip.status_code == HTTPStatus.CREATED
    assert r_trip.json() == {
        'user_id': trip.user_id,
        'func': trip.func,
        'oper': trip.oper,
        'trig': trip.trig,
        'user': {
            'username': user.username,
            'email': user.email,
            'id': 1,
        },
    }


def test_create_trip_trig_ja_existe(): ...


def test_create_trip_id_ja_existe(): ...


def test_get_unique_trip(): ...


def test_read_list_trips(): ...
