from sqlalchemy import select

from fcontrol_api.models import Funcao, Quad, Tripulante, User


def test_create_user(session):
    new_user = User(
        p_g='2s',
        esp=None,
        nome_guerra='fulano',
        nome_completo=None,
        id_fab=None,
        saram=5555555,
        unidade='11gt',
        cpf=None,
        email_fab=None,
        email_pess=None,
        nasc=None,
        ult_promo=None,
        password='secret',
    )
    session.add(new_user)
    session.commit()

    user = session.scalar(select(User).where(User.saram == '5555555'))

    assert user.nome_guerra == 'fulano'


def test_create_quad(session):
    quad = Quad(value=1, type='local', trip_id=1, description='teste')

    session.add(quad)
    session.commit()
    session.refresh(quad)

    quads = session.scalar(select(Quad).where(Quad.trip_id == 1))

    assert quads


def test_create_trip(session):
    trip = Tripulante(
        user_id=1,
        trig='RPH',
        active=True,
        uae='11gt',
    )

    session.add(trip)
    session.commit()
    session.refresh(trip)

    trip = session.scalar(select(Tripulante).where(Tripulante.trig == 'RPH'))

    assert trip


def test_create_func(session):
    funcao = Funcao(
        trip_id=1,
        func='oe',
        oper='al',
        proj='kc-390',
        data_op=None,
    )

    session.add(funcao)
    session.commit()
    session.refresh(funcao)

    funcao = session.scalar(select(Funcao).where(
        (Funcao.trip_id == 1) & (Funcao.func == 'oe')
        ))

    assert funcao
