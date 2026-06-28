"""Testes para _buscar_valor_por_dia e _buscar_soldo_por_dia."""

from datetime import date
from decimal import Decimal

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.services.custos.calculo import (
    _buscar_soldo_por_dia,
    _buscar_valor_por_dia,
)

# --- _buscar_valor_por_dia ---


def test_busca_valor_dentro_vigencia(valores_diarias_cache):
    """Retorna valor correto para data dentro do período."""
    data = date(2026, 2, 1)
    valor = _buscar_valor_por_dia(3, 1, data, valores_diarias_cache)
    assert valor == 425.00


def test_busca_valor_grupo_pg_4_grupo_cid_3(valores_diarias_cache):
    """Retorna R$ 280 para praça em cidade grupo 3."""
    data = date(2026, 2, 1)
    valor = _buscar_valor_por_dia(4, 3, data, valores_diarias_cache)
    assert valor == 280.00


def test_valor_zero_para_grupo_inexistente(valores_diarias_cache):
    """Retorna 0.0 se grupo não existe no cache."""
    data = date(2026, 2, 1)
    valor = _buscar_valor_por_dia(99, 99, data, valores_diarias_cache)
    assert valor == 0.0


def test_valor_zero_para_data_anterior_vigencia():
    """Retorna 0 se data é anterior ao início da vigência."""
    cache = {
        (3, 1): [
            DiariaValor(
                grupo_pg=3,
                grupo_cid=1,
                valor=Decimal('425.00'),
                data_inicio=date(2025, 1, 1),
                data_fim=None,
            )
        ]
    }
    data = date(2024, 12, 31)
    valor = _buscar_valor_por_dia(3, 1, data, cache)
    assert valor == Decimal('0')


# --- Fronteiras de vigência (inclusividade das datas) ---


def _faixa(valor, ini, fim):
    return DiariaValor(
        grupo_pg=3,
        grupo_cid=1,
        valor=Decimal(valor),
        data_inicio=ini,
        data_fim=fim,
    )


def test_fronteira_data_inicio_inclusiva():
    """data == data_inicio retorna o valor (limite inferior inclusivo)."""
    cache = {(3, 1): [_faixa('425.00', date(2025, 1, 1), date(2025, 12, 31))]}
    valor = _buscar_valor_por_dia(3, 1, date(2025, 1, 1), cache)
    assert valor == Decimal('425.00')


def test_fronteira_data_fim_inclusiva():
    """data == data_fim retorna o valor (limite superior inclusivo, <=)."""
    cache = {(3, 1): [_faixa('425.00', date(2025, 1, 1), date(2025, 12, 31))]}
    valor = _buscar_valor_por_dia(3, 1, date(2025, 12, 31), cache)
    assert valor == Decimal('425.00')


def test_fronteira_dia_apos_data_fim_excluido():
    """data == data_fim + 1 não casa a faixa fechada -> 0."""
    cache = {(3, 1): [_faixa('425.00', date(2025, 1, 1), date(2025, 12, 31))]}
    valor = _buscar_valor_por_dia(3, 1, date(2026, 1, 1), cache)
    assert valor == Decimal('0')


def test_multi_faixa_seleciona_correta_por_data():
    """Duas faixas fechadas adjacentes: cada data pega a faixa certa."""
    cache = {
        (3, 1): [
            _faixa('400.00', date(2024, 1, 1), date(2024, 12, 31)),
            _faixa('425.00', date(2025, 1, 1), date(2025, 12, 31)),
        ]
    }
    # Lado da faixa antiga
    assert _buscar_valor_por_dia(
        3, 1, date(2024, 6, 1), cache
    ) == Decimal('400.00')
    # Lado da faixa nova
    assert _buscar_valor_por_dia(
        3, 1, date(2025, 6, 1), cache
    ) == Decimal('425.00')
    # Última data da faixa antiga (fronteira)
    assert _buscar_valor_por_dia(
        3, 1, date(2024, 12, 31), cache
    ) == Decimal('400.00')
    # Primeira data da faixa nova (fronteira)
    assert _buscar_valor_por_dia(
        3, 1, date(2025, 1, 1), cache
    ) == Decimal('425.00')


# --- _buscar_soldo_por_dia ---


def test_busca_soldo_capitao(soldos_cache):
    """Retorna soldo correto para Capitão."""
    data = date(2026, 2, 1)
    valor = _buscar_soldo_por_dia('cp', data, soldos_cache)
    assert valor == 9976.00


def test_busca_soldo_cabo(soldos_cache):
    """Retorna soldo correto para Cabo."""
    data = date(2026, 2, 1)
    valor = _buscar_soldo_por_dia('cb', data, soldos_cache)
    assert valor == 2869.00


def test_soldo_zero_pg_inexistente(soldos_cache):
    """Retorna 0.0 se pg não existe no cache."""
    data = date(2026, 2, 1)
    valor = _buscar_soldo_por_dia('xx', data, soldos_cache)
    assert valor == 0.0
