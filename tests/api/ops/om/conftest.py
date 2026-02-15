import pytest

from fcontrol_api.models.public.aeronaves import Aeronave


@pytest.fixture(autouse=True)
async def seed_aeronaves(session):
    """Cria aeronaves necessárias para FK de matricula_anv."""
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
            sit='DI',
            obs=None,
            prox_insp=None,
        ),
        Aeronave(
            matricula='2852',
            active=True,
            sit='DI',
            obs=None,
            prox_insp=None,
        ),
    ]
    session.add_all(aeros)
    await session.commit()
