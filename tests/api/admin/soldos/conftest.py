"""
Fixtures para testes de Soldos.
"""

from datetime import date, timedelta

import pytest

from tests.factories import SoldoFactory


@pytest.fixture
async def soldos(session):
    """
    Cria soldos para testes.

    Cria 3 soldos com diferentes postos/graduacoes e circulos:
    - cb (praca) - vigente
    - 2s (grad) - vigente
    - 1t (of_sub) - expirado

    Returns:
        list[Soldo]: Lista de soldos criados
    """
    today = date.today()

    soldos_list = [
        # Soldo vigente - cabo (praca)
        SoldoFactory(
            pg='cb',
            valor=4000.00,
            data_inicio=today - timedelta(days=30),
            data_fim=None,
        ),
        # Soldo vigente - segundo sargento (grad)
        SoldoFactory(
            pg='2s',
            valor=6000.00,
            data_inicio=today - timedelta(days=60),
            data_fim=today + timedelta(days=30),
        ),
        # Soldo expirado - primeiro tenente (of_sub)
        SoldoFactory(
            pg='1t',
            valor=10000.00,
            data_inicio=today - timedelta(days=365),
            data_fim=today - timedelta(days=30),
        ),
    ]

    session.add_all(soldos_list)
    await session.commit()

    for soldo in soldos_list:
        await session.refresh(soldo)

    return soldos_list
