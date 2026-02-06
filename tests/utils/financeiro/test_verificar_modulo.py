"""Testes para verificar_modulo (afastamento > 15 dias)."""

from datetime import datetime

from fcontrol_api.utils.financeiro import verificar_modulo


def test_14_dias_consecutivos_retorna_false():
    """14 dias consecutivos não ativa módulo."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 14, 18, 0),
        }
    ]
    assert verificar_modulo(missoes) is False


def test_15_dias_consecutivos_retorna_true():
    """15 dias consecutivos ativa módulo."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 15, 18, 0),
        }
    ]
    assert verificar_modulo(missoes) is True


def test_missoes_separadas_com_gap():
    """Missões com gap não acumulam dias."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 10, 18, 0),
        },
        {
            'afast': datetime(2026, 2, 13, 8, 0),
            'regres': datetime(2026, 2, 20, 18, 0),
        },
    ]
    assert verificar_modulo(missoes) is False


def test_missoes_consecutivas_somam():
    """Missões consecutivas somam dias."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 8, 18, 0),
        },
        {
            'afast': datetime(2026, 2, 9, 8, 0),
            'regres': datetime(2026, 2, 16, 18, 0),
        },
    ]
    assert verificar_modulo(missoes) is True


def test_missoes_sobrepostas_nao_acumula():
    """
    Missões sobrepostas não contam dias duplicados.

    Datas repetidas têm diff=0 (não 1), reiniciando o contador.
    """
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 10, 18, 0),
        },
        {
            'afast': datetime(2026, 2, 8, 8, 0),
            'regres': datetime(2026, 2, 18, 18, 0),
        },
    ]
    assert verificar_modulo(missoes) is False
