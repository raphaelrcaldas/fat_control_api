"""Fator do dia, antisobreposicao e quantizacao.

O dia vale `1 / dias_do_mes` vezes o fator da categoria (A = 20%, B = 10%),
entao o mesmo dia vale mais em fevereiro que em janeiro. Quando dois trechos
cobrem o mesmo dia, paga-se o de maior valor e zera-se o outro.
"""

from datetime import date
from decimal import Decimal

from fcontrol_api.services.gle.calculo import (
    fator_do_dia,
    quantizar,
    quantizar_multiplicador,
    resolver_sobreposicao,
)

GRUPO_A = 1
GRUPO_B = 2


# --- fator_do_dia: denominador vem do mes do proprio dia ---


def test_fator_grupo_a_em_mes_de_31_dias():
    esperado = Decimal(1) / Decimal(31) * Decimal('0.20')

    assert fator_do_dia(date(2026, 1, 15), GRUPO_A) == esperado


def test_fator_grupo_b_e_metade_do_grupo_a():
    dia = date(2026, 1, 15)

    assert fator_do_dia(dia, GRUPO_B) * 2 == fator_do_dia(dia, GRUPO_A)


def test_fevereiro_comum_usa_28_dias():
    esperado = Decimal(1) / Decimal(28) * Decimal('0.20')

    assert fator_do_dia(date(2026, 2, 10), GRUPO_A) == esperado


def test_fevereiro_bissexto_usa_29_dias():
    """2024 e bissexto: o mesmo dia vale menos que em 2026."""
    bissexto = fator_do_dia(date(2024, 2, 10), GRUPO_A)
    comum = fator_do_dia(date(2026, 2, 10), GRUPO_A)

    assert bissexto == Decimal(1) / Decimal(29) * Decimal('0.20')
    # 29 dias diluem mais que 28: o dia do ano bissexto vale menos.
    assert bissexto < comum


def test_dia_de_fevereiro_vale_mais_que_dia_de_janeiro():
    """Denominador menor, fracao maior — e o efeito que a regra quer."""
    assert fator_do_dia(date(2026, 2, 10), GRUPO_A) > fator_do_dia(
        date(2026, 1, 10), GRUPO_A
    )


# --- resolver_sobreposicao ---


def _dia(d: int, fator: str) -> tuple[date, Decimal]:
    return (date(2026, 3, d), Decimal(fator))


def test_sem_sobreposicao_mantem_todos_os_fatores():
    trechos = [[_dia(10, '0.006')], [_dia(11, '0.003')]]

    assert resolver_sobreposicao(trechos) == [
        {date(2026, 3, 10): Decimal('0.006')},
        {date(2026, 3, 11): Decimal('0.003')},
    ]


def test_dia_comum_fica_com_o_trecho_de_maior_valor():
    """A (0.006) vence B (0.003) no dia 10; o B zera."""
    trechos = [[_dia(10, '0.006')], [_dia(10, '0.003')]]

    resultado = resolver_sobreposicao(trechos)

    assert resultado[0][date(2026, 3, 10)] == Decimal('0.006')
    assert resultado[1][date(2026, 3, 10)] == Decimal(0)


def test_ordem_dos_trechos_nao_altera_quem_vence():
    """O maior valor vence esteja ele em primeiro ou em segundo lugar."""
    a_primeiro = resolver_sobreposicao([
        [_dia(10, '0.006')],
        [_dia(10, '0.003')],
    ])
    b_primeiro = resolver_sobreposicao([
        [_dia(10, '0.003')],
        [_dia(10, '0.006')],
    ])

    assert a_primeiro[0][date(2026, 3, 10)] == Decimal('0.006')
    assert a_primeiro[1][date(2026, 3, 10)] == Decimal(0)
    # Invertido: agora quem paga e o segundo, mas o valor pago e o mesmo.
    assert b_primeiro[0][date(2026, 3, 10)] == Decimal(0)
    assert b_primeiro[1][date(2026, 3, 10)] == Decimal('0.006')


def test_empate_mantem_o_primeiro_trecho():
    """`>` e nao `>=`: empate e resolvido pelo trecho mais antigo."""
    trechos = [[_dia(10, '0.006')], [_dia(10, '0.006')]]

    resultado = resolver_sobreposicao(trechos)

    assert resultado[0][date(2026, 3, 10)] == Decimal('0.006')
    assert resultado[1][date(2026, 3, 10)] == Decimal(0)


def test_trechos_identicos_pagam_uma_vez_so():
    trechos = [
        [_dia(10, '0.006'), _dia(11, '0.006')],
        [_dia(10, '0.006'), _dia(11, '0.006')],
    ]

    resultado = resolver_sobreposicao(trechos)

    assert sum(resultado[0].values()) == Decimal('0.012')
    assert sum(resultado[1].values()) == Decimal(0)


def test_tres_trechos_no_mesmo_dia_pagam_uma_vez_so():
    trechos = [[_dia(10, '0.003')], [_dia(10, '0.006')], [_dia(10, '0.004')]]

    resultado = resolver_sobreposicao(trechos)

    pagos = [m[date(2026, 3, 10)] for m in resultado]
    assert pagos == [Decimal(0), Decimal('0.006'), Decimal(0)]
    assert sum(pagos) == Decimal('0.006')


def test_nenhum_dia_e_perdido_na_resolucao():
    """Todo dia informado continua presente — zerado, nunca omitido.

    A memoria de calculo mostra o dia riscado: some-lo esconderia do
    usuario que ele foi considerado.
    """
    trechos = [[_dia(10, '0.006'), _dia(11, '0.006')], [_dia(11, '0.003')]]

    resultado = resolver_sobreposicao(trechos)

    assert set(resultado[0]) == {date(2026, 3, 10), date(2026, 3, 11)}
    assert set(resultado[1]) == {date(2026, 3, 11)}
    assert resultado[1][date(2026, 3, 11)] == Decimal(0)


def test_lista_vazia_devolve_lista_vazia():
    assert resolver_sobreposicao([]) == []


# --- Quantizacao ---


def test_quantizar_arredonda_para_cima_no_meio_centavo():
    """ROUND_HALF_UP: 0.005 vira 0.01, nao 0.00 (banker's rounding)."""
    assert quantizar(Decimal('1281.295')) == Decimal('1281.30')


def test_quantizar_multiplicador_guarda_8_casas():
    assert quantizar_multiplicador(Decimal('0.213978494623')) == Decimal(
        '0.21397849'
    )


def test_quantizar_multiplicador_devolve_zero_limpo():
    """Zero volta como Decimal(0), nunca como '0E-8'.

    `normalize()` produziria "0E-8", que o front exibiria cru.
    """
    zerado = quantizar_multiplicador(Decimal(0))

    assert zerado == Decimal(0)
    assert str(zerado) == '0'
