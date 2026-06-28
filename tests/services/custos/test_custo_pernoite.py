"""Testes para _custo_pernoite."""

from datetime import date
from decimal import Decimal

from fcontrol_api.models.shared.posto_grad import Soldo
from fcontrol_api.services.custos.calculo import _custo_pernoite


def test_diaria_3_dias_sem_meia_sem_acrescimo(
    valores_diarias_cache, soldos_cache
):
    """
    3 dias (01 a 03/02), diária normal, sem meia, sem acréscimo.

    Grupo PG 3, Grupo Cidade 3: R$ 335,00/dia
    Dias 1 e 2 = completas, dia 3 = último (não conta sem meia)
    Esperado: 2 * 335 = R$ 670,00
    """
    custo = _custo_pernoite(
        pg='cp',
        sit='c',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 3),
        gp_pg=3,
        gp_cid=3,
        meia_diaria=False,
        ac_desloc=False,
        soldos_cache=soldos_cache,
        vals_cache=valores_diarias_cache,
    )

    assert custo['subtotal'] == 670.00
    assert custo['dias'] == 2
    assert custo['ac_desloc'] == 0
    assert len(custo['vals']) == 1
    assert custo['vals'][0]['valor'] == 335.00
    assert custo['vals'][0]['qtd'] == 2


def test_diaria_3_dias_com_meia_com_acrescimo(
    valores_diarias_cache, soldos_cache
):
    """
    3 dias (01 a 03/02), com meia-diária, com acréscimo.

    Grupo PG 3, Grupo Cidade 1: R$ 425,00/dia
    Esperado: 2*425 + 0.5*425 + 95 = R$ 1.157,50
    """
    custo = _custo_pernoite(
        pg='cp',
        sit='c',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 3),
        gp_pg=3,
        gp_cid=1,
        meia_diaria=True,
        ac_desloc=True,
        soldos_cache=soldos_cache,
        vals_cache=valores_diarias_cache,
    )

    assert custo['subtotal'] == 1157.50
    assert custo['dias'] == 3
    assert custo['ac_desloc'] == 95
    assert len(custo['vals']) == 1
    assert custo['vals'][0]['valor'] == 425.00
    assert custo['vals'][0]['qtd'] == 2.5


def test_gratificacao_5_dias(valores_diarias_cache, soldos_cache):
    """
    5 dias (01 a 05/02), gratificação (sit='g').

    Capitão (cp): soldo R$ 9.976,00
    Esperado: 5 * (9976 * 0.02) = R$ 997,60
    """
    custo = _custo_pernoite(
        pg='cp',
        sit='g',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 5),
        gp_pg=3,
        gp_cid=1,
        meia_diaria=False,
        ac_desloc=False,
        soldos_cache=soldos_cache,
        vals_cache=valores_diarias_cache,
    )

    # Valor exato calculado à mão: _q(9976.00 * 0.02) = 199.52 por dia.
    # 5 * 199.52 = 997.60 — sem o drift binário do float (era 997.6000...1).
    assert custo['subtotal'] == Decimal('997.60')
    assert custo['dias'] == 5
    assert custo['ac_desloc'] == 0


def test_gratificacao_round_half_up():
    """Gratificação com soldo cujo 2% cai em fração de centavo .xx5.

    Soldo R$ 5.209,37 -> 2% = 104,1874 por dia. Quantizado a centavos com
    ROUND_HALF_UP = 104,19. Para 2 dias: 208,38. Garante que o motor
    arredonda (e não trunca nem acumula em float).
    """
    data_inicio = date(2026, 1, 1)
    soldos_cache = {
        'xx': [
            Soldo(
                pg='xx',
                valor=Decimal('5209.37'),
                data_inicio=data_inicio,
                data_fim=None,
            )
        ]
    }

    custo = _custo_pernoite(
        pg='xx',
        sit='g',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 2),
        gp_pg=3,
        gp_cid=1,
        meia_diaria=False,
        ac_desloc=False,
        soldos_cache=soldos_cache,
        vals_cache={},
    )

    # 5209.37 * 0.02 = 104.1874 -> ROUND_HALF_UP a centavos = 104.19/dia
    assert custo['vals'][0]['valor'] == Decimal('104.19')
    assert custo['subtotal'] == Decimal('208.38')
    assert custo['dias'] == 2


def test_diaria_1_dia_sem_meia(valores_diarias_cache, soldos_cache):
    """
    1 dia apenas (01/02), sem meia-diária.

    É o último dia, sem meia = nenhuma diária. Esperado: R$ 0,00
    """
    custo = _custo_pernoite(
        pg='cp',
        sit='c',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 1),
        gp_pg=3,
        gp_cid=3,
        meia_diaria=False,
        ac_desloc=False,
        soldos_cache=soldos_cache,
        vals_cache=valores_diarias_cache,
    )

    assert custo['subtotal'] == 0.0
    assert custo['dias'] == 0


def test_diaria_1_dia_com_meia(valores_diarias_cache, soldos_cache):
    """
    1 dia apenas (01/02), com meia-diária.

    Grupo PG 3, Grupo Cidade 3: R$ 335,00
    Esperado: 335 * 0.5 = R$ 167,50
    """
    custo = _custo_pernoite(
        pg='cp',
        sit='c',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 1),
        gp_pg=3,
        gp_cid=3,
        meia_diaria=True,
        ac_desloc=False,
        soldos_cache=soldos_cache,
        vals_cache=valores_diarias_cache,
    )

    assert custo['subtotal'] == 167.50
    assert custo['dias'] == 1


def test_praca_grupo_cidade_3(valores_diarias_cache, soldos_cache):
    """
    Praça (cb, grupo 4) em cidade grupo 3.

    2 dias (01 a 02/02), sem meia, sem acréscimo.
    Esperado: 1 * 280 = R$ 280,00 (dia 2 é o último)
    """
    custo = _custo_pernoite(
        pg='cb',
        sit='c',
        ini=date(2026, 2, 1),
        fim=date(2026, 2, 2),
        gp_pg=4,
        gp_cid=3,
        meia_diaria=False,
        ac_desloc=False,
        soldos_cache=soldos_cache,
        vals_cache=valores_diarias_cache,
    )

    assert custo['subtotal'] == 280.00
    assert custo['dias'] == 1
