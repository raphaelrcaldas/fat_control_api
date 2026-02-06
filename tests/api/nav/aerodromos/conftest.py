"""
Fixtures para testes de Aerodromos.

Os dados de seed (estados, cidades) estao centralizados em
tests/seed/ e sao carregados automaticamente.
"""

import pytest

from tests.factories import AerodromoFactory


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
