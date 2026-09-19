"""Fixtures das missoes de GLE.

Boa Vista/RR (grupo A) e a localidade do caso real da planilha GLEE, que os
testes de valor reproduzem ate o centavo.
"""

import pytest

from tests.factories import GrupoLocEspFactory, LocEspIcaoFactory

BOA_VISTA = 1400100  # RR, grupo A no caso real
PALMAS = 1721000  # TO, usada como grupo B


@pytest.fixture
async def loc_a(session):
    """Boa Vista/RR, grupo A (20%)."""
    loc = GrupoLocEspFactory(cidade_id=BOA_VISTA, grupo=1, fuso=-4)
    session.add(loc)
    await session.commit()
    await session.refresh(loc)
    return loc


@pytest.fixture
async def loc_b(session):
    """Palmas/TO, grupo B (10%)."""
    loc = GrupoLocEspFactory(cidade_id=PALMAS, grupo=2, fuso=-3)
    session.add(loc)
    await session.commit()
    await session.refresh(loc)
    return loc


@pytest.fixture
async def loc_a_com_icao(session, loc_a):
    """Boa Vista com o ICAO SBBV, para a pesquisa cruzar com etapa."""
    session.add(LocEspIcaoFactory(loc_esp_id=loc_a.id, icao='SBBV'))
    await session.commit()
    return loc_a
