"""
Fixtures para testes de Aerodromos.
"""

import pytest

from fcontrol_api.models.public.estados_cidades import Cidade, Estado
from tests.factories import AerodromoFactory


@pytest.fixture(autouse=True)
async def seed_estados_cidades(session):
    """Insere estados e cidades para testes com codigo_cidade."""
    estados = [
        Estado(codigo_uf=35, nome='São Paulo', uf='SP'),
        Estado(codigo_uf=53, nome='Distrito Federal', uf='DF'),
    ]
    session.add_all(estados)
    await session.flush()

    cidades = [
        Cidade(codigo=3550308, nome='São Paulo', uf='SP'),
        Cidade(codigo=5300108, nome='Brasília', uf='DF'),
    ]
    session.add_all(cidades)
    await session.flush()


@pytest.fixture
async def aerodromos(session):
    """
    Cria aerodromos para testes.

    Returns:
        list[Aerodromo]: Lista de aerodromos criados
    """
    aerodromos_list = [
        AerodromoFactory(
            nome='Aeroporto de Congonhas',
            codigo_icao='SBSP',
            codigo_iata='CGH',
            latitude=-23.6261,
            longitude=-46.6564,
            elevacao=802.0,
            pais='BR',
            utc=-3,
            codigo_cidade=3550308,
        ),
        AerodromoFactory(
            nome='Aeroporto de Brasília',
            codigo_icao='SBBR',
            codigo_iata='BSB',
            latitude=-15.8711,
            longitude=-47.9186,
            elevacao=1066.0,
            pais='BR',
            utc=-3,
            base_aerea={'nome': 'Base Aérea de Brasília', 'sigla': 'BABR'},
            codigo_cidade=5300108,
        ),
        AerodromoFactory(
            nome='Aeroporto Internacional',
            codigo_icao='SBGL',
            codigo_iata='GIG',
            latitude=-22.8090,
            longitude=-43.2506,
            elevacao=9.0,
            pais='BR',
            utc=-3,
            cidade_manual='Rio de Janeiro',
        ),
    ]

    session.add_all(aerodromos_list)
    await session.commit()

    for aerodromo in aerodromos_list:
        await session.refresh(aerodromo)

    return aerodromos_list
