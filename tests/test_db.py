from sqlalchemy import select

from fcontrol_api.models import Quad, Tripulante, User


def test_create_user(session):
    new_user = User(username='alice', password='secret', email='teste@test')
    session.add(new_user)
    session.commit()

    user = session.scalar(select(User).where(User.username == 'alice'))

    assert user.username == 'alice'


def test_create_quad(session):
    quad = Quad(value=1, type='local', user_id=1)

    session.add(quad)
    session.commit()
    session.refresh(quad)

    quads = session.scalar(select(Quad).where(Quad.user_id == 1))

    assert quads


def test_create_trip(session):
    trip = Tripulante(user_id=1, trig='RPH', func='oe', oper='AL', active=True)

    session.add(trip)
    session.commit()
    session.refresh(trip)

    trip = session.scalar(select(Tripulante).where(Tripulante.trig == 'RPH'))

    assert trip
