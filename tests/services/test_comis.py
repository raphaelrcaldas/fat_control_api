"""Testes para verificar_modulo (afastamento >= 16 dias)."""

from datetime import datetime

from fcontrol_api.services.comis import verificar_modulo


def test_14_dias_consecutivos_retorna_false():
    """14 dias consecutivos não ativa módulo."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 14, 18, 0),
        }
    ]
    assert verificar_modulo(missoes) is False


def test_15_dias_consecutivos_retorna_false():
    """15 dias consecutivos não ativa módulo (limite é 16)."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 15, 18, 0),
        }
    ]
    assert verificar_modulo(missoes) is False


def test_16_dias_consecutivos_retorna_true():
    """16 dias consecutivos ativa módulo."""
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 16, 18, 0),
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


def test_missoes_sobrepostas_nao_inflam_a_contagem():
    """Sobreposição não conta o mesmo dia duas vezes.

    10 dias (01→10) + 8 dias (05→12) somam 18 na conta ingênua, o que
    ativaria o módulo. Mas o militar ficou afastado de 01 a 12 — 12 dias
    corridos. O que conta é a UNIÃO das datas, não a soma dos intervalos.
    """
    missoes = [
        {
            'afast': datetime(2026, 2, 1, 8, 0),
            'regres': datetime(2026, 2, 10, 18, 0),
        },
        {
            'afast': datetime(2026, 2, 5, 8, 0),
            'regres': datetime(2026, 2, 12, 18, 0),
        },
    ]
    assert verificar_modulo(missoes) is False


def test_missoes_sobrepostas_uniao_contigua_ativa_modulo():
    """A união de missões sobrepostas conta como afastamento contínuo.

    01→10 e 08→18 se sobrepõem, mas cobrem 01 a 18 de fevereiro sem buraco:
    18 dias corridos fora de casa, logo o módulo é ativado. É o outro lado da
    dedup — ela impede inflar a contagem, não zerá-la: antes do `set`, a data
    repetida dava `dif == 0` e reiniciava o contador, e módulos reais de 16+
    dias passavam despercebidos.
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
    assert verificar_modulo(missoes) is True
