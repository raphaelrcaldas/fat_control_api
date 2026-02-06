"""Fixtures compartilhadas para testes de fcontrol_api/utils/financeiro.py.

Dados reais extraídos do Supabase (seed data) para cálculos verificáveis.
"""

from datetime import date

import pytest

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.public.posto_grad import Soldo


@pytest.fixture
def valores_diarias_cache():
    """
    Cache de valores de diárias por (grupo_pg, grupo_cid).

    Valores reais vigentes desde 2025-01-01.
    """
    data_inicio = date(2025, 1, 1)

    def _criar_diaria(grupo_pg, grupo_cid, valor):
        return DiariaValor(
            grupo_pg=grupo_pg,
            grupo_cid=grupo_cid,
            valor=valor,
            data_inicio=data_inicio,
            data_fim=None,
        )

    return {
        # Grupo PG 1 (Oficiais Generais)
        (1, 1): [_criar_diaria(1, 1, 600.00)],
        (1, 2): [_criar_diaria(1, 2, 515.00)],
        (1, 3): [_criar_diaria(1, 3, 455.00)],
        # Grupo PG 2 (Oficiais Superiores)
        (2, 1): [_criar_diaria(2, 1, 510.00)],
        (2, 2): [_criar_diaria(2, 2, 450.00)],
        (2, 3): [_criar_diaria(2, 3, 395.00)],
        # Grupo PG 3 (Oficiais Int/Sub e Graduados)
        (3, 1): [_criar_diaria(3, 1, 425.00)],
        (3, 2): [_criar_diaria(3, 2, 380.00)],
        (3, 3): [_criar_diaria(3, 3, 335.00)],
        # Grupo PG 4 (Praças)
        (4, 1): [_criar_diaria(4, 1, 355.00)],
        (4, 2): [_criar_diaria(4, 2, 315.00)],
        (4, 3): [_criar_diaria(4, 3, 280.00)],
    }


@pytest.fixture
def soldos_cache():
    """
    Cache de soldos por pg_short.

    Valores reais vigentes desde 2026-01-01.
    """
    data_inicio = date(2026, 1, 1)

    def _criar_soldo(pg, valor):
        return Soldo(
            pg=pg,
            valor=valor,
            data_inicio=data_inicio,
            data_fim=None,
        )

    return {
        '1s': [_criar_soldo('1s', 5988.00)],
        '1t': [_criar_soldo('1t', 9004.00)],
        '2s': [_criar_soldo('2s', 5209.00)],
        '2t': [_criar_soldo('2t', 8179.00)],
        '3s': [_criar_soldo('3s', 4177.00)],
        'cb': [_criar_soldo('cb', 2869.00)],
        'cl': [_criar_soldo('cl', 12505.00)],
        'cp': [_criar_soldo('cp', 9976.00)],
        'mb': [_criar_soldo('mb', 14100.00)],
        'mj': [_criar_soldo('mj', 12108.00)],
        'so': [_criar_soldo('so', 6737.00)],
        'tc': [_criar_soldo('tc', 12285.00)],
    }


@pytest.fixture
def grupos_pg():
    """Mapeamento pg_short -> grupo_pg."""
    return {
        # Grupo 1 - Oficiais Generais
        'br': 1,
        'mb': 1,
        'tb': 1,
        # Grupo 2 - Oficiais Superiores
        'cl': 2,
        'mj': 2,
        'tc': 2,
        # Grupo 3 - Oficiais Int/Sub e Graduados
        '1s': 3,
        '1t': 3,
        '2s': 3,
        '2t': 3,
        '3s': 3,
        'cp': 3,
        'so': 3,
        # Grupo 4 - Praças
        'cb': 4,
        's1': 4,
        's2': 4,
    }


@pytest.fixture
def grupos_cidade():
    """Mapeamento cidade_codigo -> grupo_cidade."""
    return {
        # Grupo 1 - Capitais especiais
        1302603: 1,  # Manaus
        3304557: 1,  # Rio de Janeiro
        3550308: 1,  # São Paulo
        5300108: 1,  # Brasília
        # Grupo 2 - Demais capitais
        2927408: 2,  # Salvador
        3106200: 2,  # Belo Horizonte
        4106902: 2,  # Curitiba
        # Grupo 3 = default para demais localidades
    }
