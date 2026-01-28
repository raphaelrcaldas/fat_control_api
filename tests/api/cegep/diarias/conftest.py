"""
Fixtures para testes de Diarias.
"""

from datetime import date, timedelta

import pytest

from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.public.estados_cidades import Cidade, Estado
from tests.factories import DiariaValorFactory


@pytest.fixture(autouse=True)
async def seed_diarias_data(session):
    """
    Insere dados necessarios para testes de diarias.

    Inclui estados, cidades, grupos de cidade e grupos de P/G.
    """
    # Estados
    estados = [
        Estado(codigo_uf=35, nome='São Paulo', uf='SP'),
        Estado(codigo_uf=33, nome='Rio de Janeiro', uf='RJ'),
        Estado(codigo_uf=53, nome='Distrito Federal', uf='DF'),
    ]
    session.add_all(estados)
    await session.flush()

    # Cidades
    cidades = [
        Cidade(codigo=3550308, nome='São Paulo', uf='SP'),
        Cidade(codigo=3304557, nome='Rio de Janeiro', uf='RJ'),
        Cidade(codigo=5300108, nome='Brasília', uf='DF'),
    ]
    session.add_all(cidades)
    await session.flush()

    # Grupos de Cidade (1=Capital, 2=Interior)
    grupos_cidade = [
        GrupoCidade(grupo=1, cidade_id=3550308),  # SP - Capital
        GrupoCidade(grupo=1, cidade_id=3304557),  # RJ - Capital
        GrupoCidade(grupo=1, cidade_id=5300108),  # BSB - Capital
    ]
    session.add_all(grupos_cidade)
    await session.flush()

    # Grupos de P/G (1=Oficiais, 2=Graduados, 3=Pracas)
    grupos_pg = [
        GrupoPg(grupo=1, pg_short='1t'),  # Oficiais
        GrupoPg(grupo=1, pg_short='cp'),  # Oficiais
        GrupoPg(grupo=2, pg_short='2s'),  # Graduados
        GrupoPg(grupo=2, pg_short='3s'),  # Graduados
        GrupoPg(grupo=3, pg_short='cb'),  # Pracas
    ]
    session.add_all(grupos_pg)
    await session.flush()


@pytest.fixture
async def diaria_valores(session):
    """
    Cria valores de diarias para testes.

    Cria 3 valores com diferentes status:
    - vigente (data_inicio passado, data_fim futuro ou None)
    - anterior (data_fim passado)
    - proximo (data_inicio futuro)

    Returns:
        list[DiariaValor]: Lista de valores criados
    """
    today = date.today()

    valores = [
        # Valor vigente - sem data_fim
        DiariaValorFactory(
            grupo_pg=1,
            grupo_cid=1,
            valor=300.00,
            data_inicio=today - timedelta(days=30),
            data_fim=None,
        ),
        # Valor vigente - com data_fim futura
        DiariaValorFactory(
            grupo_pg=2,
            grupo_cid=1,
            valor=250.00,
            data_inicio=today - timedelta(days=60),
            data_fim=today + timedelta(days=30),
        ),
        # Valor anterior (expirado)
        DiariaValorFactory(
            grupo_pg=3,
            grupo_cid=1,
            valor=200.00,
            data_inicio=today - timedelta(days=365),
            data_fim=today - timedelta(days=30),
        ),
        # Valor proximo (futuro)
        DiariaValorFactory(
            grupo_pg=1,
            grupo_cid=1,
            valor=350.00,
            data_inicio=today + timedelta(days=30),
            data_fim=None,
        ),
    ]

    session.add_all(valores)
    await session.commit()

    for valor in valores:
        await session.refresh(valor)

    return valores
