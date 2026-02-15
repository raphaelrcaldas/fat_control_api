import pytest

from fcontrol_api.models.public.aeronaves import Aeronave


@pytest.fixture
async def aeronave(session):
    """Cria uma aeronave no banco de dados."""
    aero = Aeronave(
        matricula='2850',
        active=True,
        sit='DI',
        obs=None,
        prox_insp=None,
    )
    session.add(aero)
    await session.commit()
    await session.refresh(aero)
    return aero


@pytest.fixture
async def aeronaves(session):
    """Cria múltiplas aeronaves no banco de dados."""
    aeros = [
        Aeronave(
            matricula='2850',
            active=True,
            sit='DI',
            obs=None,
            prox_insp=None,
        ),
        Aeronave(
            matricula='2851',
            active=True,
            sit='DO',
            obs='Motor direito em observação',
            prox_insp=None,
        ),
        Aeronave(
            matricula='2852',
            active=False,
            sit='IN',
            obs='Em manutenção corretiva',
            prox_insp=None,
        ),
    ]
    session.add_all(aeros)
    await session.commit()

    for a in aeros:
        await session.refresh(a)

    return aeros
