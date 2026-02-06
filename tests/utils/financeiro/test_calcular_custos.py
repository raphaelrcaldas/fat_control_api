"""Testes para calcular_custos_frag_mis."""

from datetime import date

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.utils.financeiro import calcular_custos_frag_mis


def test_missao_simples_um_usuario_um_pernoite(
    valores_diarias_cache, soldos_cache, grupos_pg, grupos_cidade
):
    """
    1 usuário (Capitão comissionado) e 1 pernoite.

    Pernoite: 01 a 03/02/2026, São Paulo (grupo 1), sem meia.
    Esperado: 2 diárias de R$ 425 = R$ 850
    """
    frag_mis = CustoFragMisInput(acrec_desloc=False)
    users_frag = [
        CustoUserFragInput(p_g=PostoGradEnum.CP, sit='c'),
    ]
    pernoites = [
        CustoPernoiteInput(
            id=1,
            data_ini=date(2026, 2, 1),
            data_fim=date(2026, 2, 3),
            meia_diaria=False,
            acrec_desloc=False,
            cidade_codigo=3550308,
        ),
    ]

    resultado = calcular_custos_frag_mis(
        frag_mis=frag_mis,
        users_frag=users_frag,
        pernoites=pernoites,
        grupos_pg=grupos_pg,
        grupos_cidade=grupos_cidade,
        valores_cache=valores_diarias_cache,
        soldos_cache=soldos_cache,
    )

    assert resultado['total_dias'] == 2
    assert resultado['acrec_desloc_missao'] == 0
    assert 'pg_cp_sit_c' in resultado['totais_pg_sit']
    total = resultado['totais_pg_sit']['pg_cp_sit_c']['total_valor']
    assert total == 850.00

    pnt = resultado['pernoite_1']
    assert pnt['grupo_cid'] == 1
    assert pnt['dias'] == 2
    assert pnt['pg_cp_sit_c']['subtotal'] == 850.00


def test_dois_usuarios_diferentes(
    valores_diarias_cache, soldos_cache, grupos_pg, grupos_cidade
):
    """
    Capitão (comissionado) e Cabo (comissionado).

    Pernoite: 01 a 03/02/2026, cidade grupo 3, sem meia.
    Capitão (grupo 3): 2 * 335 = 670
    Cabo (grupo 4): 2 * 280 = 560
    """
    frag_mis = CustoFragMisInput(acrec_desloc=False)
    users_frag = [
        CustoUserFragInput(p_g=PostoGradEnum.CP, sit='c'),
        CustoUserFragInput(p_g=PostoGradEnum.CB, sit='c'),
    ]
    pernoites = [
        CustoPernoiteInput(
            id=1,
            data_ini=date(2026, 2, 1),
            data_fim=date(2026, 2, 3),
            meia_diaria=False,
            acrec_desloc=False,
            cidade_codigo=9999999,
        ),
    ]

    resultado = calcular_custos_frag_mis(
        frag_mis=frag_mis,
        users_frag=users_frag,
        pernoites=pernoites,
        grupos_pg=grupos_pg,
        grupos_cidade=grupos_cidade,
        valores_cache=valores_diarias_cache,
        soldos_cache=soldos_cache,
    )

    totais = resultado['totais_pg_sit']
    assert totais['pg_cp_sit_c']['total_valor'] == 670.00
    assert totais['pg_cb_sit_c']['total_valor'] == 560.00


def test_missao_com_gratificacao(
    valores_diarias_cache, soldos_cache, grupos_pg, grupos_cidade
):
    """
    1 usuário em gratificação (sit='g').

    Capitão (soldo R$ 9.976): 2% por dia
    3 dias: 3 * 199.52 = 598.56
    """
    frag_mis = CustoFragMisInput(acrec_desloc=False)
    users_frag = [
        CustoUserFragInput(p_g=PostoGradEnum.CP, sit='g'),
    ]
    pernoites = [
        CustoPernoiteInput(
            id=1,
            data_ini=date(2026, 2, 1),
            data_fim=date(2026, 2, 3),
            meia_diaria=False,
            acrec_desloc=False,
            cidade_codigo=3550308,
        ),
    ]

    resultado = calcular_custos_frag_mis(
        frag_mis=frag_mis,
        users_frag=users_frag,
        pernoites=pernoites,
        grupos_pg=grupos_pg,
        grupos_cidade=grupos_cidade,
        valores_cache=valores_diarias_cache,
        soldos_cache=soldos_cache,
    )

    expected = 3 * (9976.00 * 0.02)
    total = resultado['totais_pg_sit']['pg_cp_sit_g']['total_valor']
    assert total == expected
    assert resultado['pernoite_1']['dias'] == 3


def test_missao_com_acrescimo_deslocamento(
    valores_diarias_cache, soldos_cache, grupos_pg, grupos_cidade
):
    """Acréscimo de deslocamento na missão e no pernoite."""
    frag_mis = CustoFragMisInput(acrec_desloc=True)
    users_frag = [
        CustoUserFragInput(p_g=PostoGradEnum.CP, sit='c'),
    ]
    pernoites = [
        CustoPernoiteInput(
            id=1,
            data_ini=date(2026, 2, 1),
            data_fim=date(2026, 2, 2),
            meia_diaria=True,
            acrec_desloc=True,
            cidade_codigo=3550308,
        ),
    ]

    resultado = calcular_custos_frag_mis(
        frag_mis=frag_mis,
        users_frag=users_frag,
        pernoites=pernoites,
        grupos_pg=grupos_pg,
        grupos_cidade=grupos_cidade,
        valores_cache=valores_diarias_cache,
        soldos_cache=soldos_cache,
    )

    assert resultado['acrec_desloc_missao'] == 95
    assert resultado['pernoite_1']['ac_desloc'] == 95
    # 425 + 212.5 + 95 = R$ 732,50
    assert (
        resultado['pernoite_1']['pg_cp_sit_c']['subtotal'] == 732.50
    )


def test_multiplos_pernoites(
    valores_diarias_cache, soldos_cache, grupos_pg, grupos_cidade
):
    """2 pernoites em cidades diferentes."""
    frag_mis = CustoFragMisInput(acrec_desloc=False)
    users_frag = [
        CustoUserFragInput(p_g=PostoGradEnum.CP, sit='c'),
    ]
    pernoites = [
        CustoPernoiteInput(
            id=1,
            data_ini=date(2026, 2, 1),
            data_fim=date(2026, 2, 3),
            meia_diaria=False,
            acrec_desloc=False,
            cidade_codigo=3550308,
        ),
        CustoPernoiteInput(
            id=2,
            data_ini=date(2026, 2, 3),
            data_fim=date(2026, 2, 5),
            meia_diaria=True,
            acrec_desloc=False,
            cidade_codigo=9999999,
        ),
    ]

    resultado = calcular_custos_frag_mis(
        frag_mis=frag_mis,
        users_frag=users_frag,
        pernoites=pernoites,
        grupos_pg=grupos_pg,
        grupos_cidade=grupos_cidade,
        valores_cache=valores_diarias_cache,
        soldos_cache=soldos_cache,
    )

    # Pernoite 1: 2 * 425 = 850
    assert (
        resultado['pernoite_1']['pg_cp_sit_c']['subtotal'] == 850.00
    )
    # Pernoite 2: 2*335 + 0.5*335 = 837.50
    assert (
        resultado['pernoite_2']['pg_cp_sit_c']['subtotal'] == 837.50
    )
    total = resultado['totais_pg_sit']['pg_cp_sit_c']['total_valor']
    assert total == 850.00 + 837.50
