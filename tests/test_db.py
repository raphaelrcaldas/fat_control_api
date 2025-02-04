import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.models import Funcao, Quad, Tripulante, User

pytestmark = pytest.mark.anyio


async def test_create_user(session):
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
        ant_rel=None,
        password='secret',
    )
    session.add(new_user)
    await session.commit()

    user = await session.scalar(select(User).where(User.saram == '5555555'))

    assert user.nome_guerra == 'fulano'


async def test_create_quad(session):
    quad = Quad(value=None, type='local', trip_id=1, description='teste')

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    quads = await session.scalar(select(Quad).where(Quad.trip_id == 1))

    assert quads


async def test_create_trip(session):
    trip = Tripulante(
        user_id=1,
        trig='RPH',
        active=True,
        uae='11gt',
    )

    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    trip = await session.scalar(
        select(Tripulante).where(Tripulante.trig == 'RPH')
    )

    assert trip


async def test_create_func(session):
    funcao = Funcao(
        trip_id=1,
        func='oe',
        oper='al',
        proj='kc-390',
        data_op=None,
    )

    session.add(funcao)
    await session.commit()
    await session.refresh(funcao)

    funcao = await session.scalar(
        select(Funcao).where((Funcao.trip_id == 1) & (Funcao.func == 'oe'))
    )

    assert funcao
