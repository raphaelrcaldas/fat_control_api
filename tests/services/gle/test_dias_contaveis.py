"""Quais dias do periodo geram gratificacao (regra das 8 horas).

O criterio vale so para as **pontas**: dia intermediario e integral. Quando
ida e volta caem no mesmo dia ha uma ponta so, e o que conta e a duracao
total da permanencia. Ver `docs/dominio/gle.md`.
"""

from datetime import date, datetime
from decimal import Decimal

from fcontrol_api.services.gle_calculo import dias_contaveis


def _dias(chegada: datetime, afastamento: datetime) -> list[date]:
    return [dia for dia, _ in dias_contaveis(chegada, afastamento)]


# --- Caso real da planilha GLEE ---


def test_caso_real_da_planilha_conta_33_dias():
    """Boa Vista/RR: 26/04 14:15 -> 29/05 02:35 = 33 dias contaveis.

    E o caso de referencia documentado: a chegada conta (sobram 9h45 ate a
    meia-noite) e o afastamento nao (so 2h35 desde a meia-noite).
    """
    dias = _dias(datetime(2026, 4, 26, 14, 15), datetime(2026, 5, 29, 2, 35))

    assert len(dias) == 33
    assert dias[0] == date(2026, 4, 26)
    assert dias[-1] == date(2026, 5, 28)
    assert date(2026, 5, 29) not in dias


# --- Fronteira das 8 horas na chegada ---


def test_chegada_com_8h_exatas_conta():
    """16:00 deixa exatamente 8h ate a meia-noite: o limite e inclusivo."""
    dias = _dias(datetime(2026, 3, 10, 16, 0), datetime(2026, 3, 12, 20, 0))

    assert date(2026, 3, 10) in dias


def test_chegada_com_7h59_nao_conta():
    """Um minuto a menos e o dia da chegada cai fora."""
    dias = _dias(datetime(2026, 3, 10, 16, 1), datetime(2026, 3, 12, 20, 0))

    assert date(2026, 3, 10) not in dias
    assert date(2026, 3, 11) in dias


# --- Fronteira das 8 horas no afastamento ---


def test_afastamento_com_8h_exatas_conta():
    dias = _dias(datetime(2026, 3, 10, 6, 0), datetime(2026, 3, 12, 8, 0))

    assert date(2026, 3, 12) in dias


def test_afastamento_com_7h59_nao_conta():
    dias = _dias(datetime(2026, 3, 10, 6, 0), datetime(2026, 3, 12, 7, 59))

    assert date(2026, 3, 12) not in dias
    assert date(2026, 3, 11) in dias


# --- Mesmo dia: uma ponta so ---


def test_mesmo_dia_com_8h_conta_uma_vez():
    dias = dias_contaveis(
        datetime(2026, 3, 10, 6, 0), datetime(2026, 3, 10, 14, 0)
    )

    assert [dia for dia, _ in dias] == [date(2026, 3, 10)]
    assert dias[0][1] == Decimal(8)


def test_mesmo_dia_com_menos_de_8h_nao_conta():
    assert (
        dias_contaveis(
            datetime(2026, 3, 10, 6, 0), datetime(2026, 3, 10, 13, 59)
        )
        == []
    )


# --- Dias intermediarios ---


def test_intermediario_e_integral_sem_teste_de_horas():
    """Dia inteiro dentro do periodo conta 24h, sem criterio de 8h."""
    dias = dias_contaveis(
        datetime(2026, 3, 10, 23, 0), datetime(2026, 3, 13, 1, 0)
    )

    assert dict(dias)[date(2026, 3, 11)] == Decimal(24)
    assert dict(dias)[date(2026, 3, 12)] == Decimal(24)
    # As duas pontas ficam de fora: 1h de cada lado.
    assert date(2026, 3, 10) not in dict(dias)
    assert date(2026, 3, 13) not in dict(dias)


# --- Periodos degenerados ---


def test_afastamento_anterior_a_chegada_nao_conta_nada():
    assert (
        dias_contaveis(
            datetime(2026, 3, 12, 6, 0), datetime(2026, 3, 10, 6, 0)
        )
        == []
    )


def test_afastamento_igual_a_chegada_nao_conta_nada():
    momento = datetime(2026, 3, 10, 6, 0)

    assert dias_contaveis(momento, momento) == []


def test_trecho_de_um_minuto_nao_conta_nada():
    assert (
        dias_contaveis(
            datetime(2026, 3, 10, 6, 0), datetime(2026, 3, 10, 6, 1)
        )
        == []
    )


# --- Virada de mes e de ano ---


def test_periodo_atravessa_a_virada_do_mes():
    dias = _dias(datetime(2026, 1, 30, 6, 0), datetime(2026, 2, 2, 20, 0))

    assert dias == [
        date(2026, 1, 30),
        date(2026, 1, 31),
        date(2026, 2, 1),
        date(2026, 2, 2),
    ]


def test_periodo_atravessa_a_virada_do_ano():
    dias = _dias(datetime(2025, 12, 30, 6, 0), datetime(2026, 1, 2, 20, 0))

    assert dias[0] == date(2025, 12, 30)
    assert dias[-1] == date(2026, 1, 2)
    assert date(2026, 1, 1) in dias
