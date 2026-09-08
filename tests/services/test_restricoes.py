from datetime import date

import pytest

from fcontrol_api.services.restricoes import (
    calcular_restricoes_derivadas,
    elegivel_desadaptacao,
)


def _por_codigo(**kwargs):
    return {
        item.codigo: item for item in calcular_restricoes_derivadas(**kwargs)
    }


def test_cemal_vence_no_dia_seguinte_e_desadaptacao_comeca_no_dia_45():
    restricoes = _por_codigo(
        cemal=date(2026, 9, 7),
        ultimo_voo=date(2026, 7, 25),
        funcao='pil',
        operacionalidade='op',
    )

    assert restricoes['cemal_vencido'].inicio == date(2026, 9, 8)
    assert restricoes['cemal_vencido'].efeito == 'bloqueio'
    assert restricoes['desadaptacao'].inicio == date(2026, 9, 8)
    assert restricoes['desadaptacao'].efeito == 'aviso'
    assert all(item.fim is None for item in restricoes.values())


def test_cemal_ausente_tem_inicio_e_fim_desconhecidos():
    restricoes = _por_codigo(
        cemal=None,
        ultimo_voo=None,
        funcao='pil',
        operacionalidade='op',
    )

    assert set(restricoes) == {'cemal_ausente'}
    assert restricoes['cemal_ausente'].inicio is None
    assert restricoes['cemal_ausente'].fim is None


@pytest.mark.parametrize(
    ('funcao', 'operacionalidade'),
    [('oe', 'op'), ('os', 'op'), ('pil', 'al')],
)
def test_excecoes_nao_geram_desadaptacao(funcao, operacionalidade):
    assert not elegivel_desadaptacao(
        funcao=funcao, operacionalidade=operacionalidade
    )

    restricoes = _por_codigo(
        cemal=date(2026, 12, 31),
        ultimo_voo=date(2026, 1, 1),
        funcao=funcao,
        operacionalidade=operacionalidade,
    )

    assert 'desadaptacao' not in restricoes


def test_funcao_operacional_e_elegivel_mesmo_sem_ultimo_voo():
    assert elegivel_desadaptacao(funcao='pil', operacionalidade='op')


def test_sem_ultimo_voo_nao_gera_desadaptacao():
    restricoes = _por_codigo(
        cemal=date(2026, 12, 31),
        ultimo_voo=None,
        funcao='pil',
        operacionalidade='op',
    )

    assert 'desadaptacao' not in restricoes


def test_datas_sem_inicio_representavel_nao_extrapolam_date_max():
    restricoes = calcular_restricoes_derivadas(
        cemal=date.max,
        ultimo_voo=date.max,
        funcao='pil',
        operacionalidade='op',
    )

    assert restricoes == []
