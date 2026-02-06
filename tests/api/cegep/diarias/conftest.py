"""
Fixtures para testes de Diarias.

Os dados de seed (estados, cidades, grupos_cidade, grupos_pg) estao
centralizados em tests/seed/ e sao carregados automaticamente.
"""

from datetime import date, timedelta

import pytest

from tests.factories import DiariaValorFactory


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
