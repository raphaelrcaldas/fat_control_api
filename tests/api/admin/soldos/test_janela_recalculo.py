"""Testes de `_janela_recalculo` (menor janela de datas a recalcular).

Editar um soldo invalida o custo das missões cuja data caiu de um soldo
para outro — e só delas. Recalcular a união das vigências (antiga ∪ nova)
era correto porém caro: mexer na `data_fim` de um soldo que vige desde
2019 varria seis anos de missões.

Testes puros (sem banco): a função é decisão sobre datas, não I/O.
"""

from datetime import date
from decimal import Decimal

from fcontrol_api.models.shared.posto_grad import Soldo
from fcontrol_api.routers.admin.soldos import _janela_recalculo


def _soldo(data_inicio, data_fim, *, pg='cb', valor='4000.00'):
    return Soldo(
        pg=pg,
        valor=Decimal(valor),
        data_inicio=data_inicio,
        data_fim=data_fim,
    )


def test_sem_mudanca_retorna_none():
    """Submit que reenvia os mesmos valores não recalcula nada.

    O formulário do front manda os quatro campos a cada submit, então
    `exclude_unset` não distingue "reenviado igual" de "alterado" — a
    comparação tem de ser contra o banco.
    """
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(
        soldo,
        {
            'pg': 'cb',
            'valor': Decimal('4000.00'),
            'data_inicio': date(2019, 1, 1),
            'data_fim': date(2025, 3, 31),
        },
    )

    assert janela is None


def test_mudanca_de_valor_cobre_a_vigencia_inteira():
    """Trocar o valor muda o custo de todos os dias da faixa."""
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(soldo, {'valor': Decimal('5000.00')})

    assert janela == (date(2019, 1, 1), date(2025, 3, 31))


def test_mudanca_de_pg_cobre_a_vigencia_inteira():
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(soldo, {'pg': '3s'})

    assert janela == (date(2019, 1, 1), date(2025, 3, 31))


def test_mudanca_de_valor_em_vigencia_aberta_fica_aberta():
    soldo = _soldo(date(2019, 1, 1), None)

    janela = _janela_recalculo(soldo, {'valor': Decimal('5000.00')})

    assert janela == (date(2019, 1, 1), None)


def test_fim_estendido_cobre_so_o_trecho_novo():
    """O ganho: 2019→2025 vira uma janela de um dia."""
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(soldo, {'data_fim': date(2025, 4, 30)})

    assert janela == (date(2025, 3, 31), date(2025, 4, 30))


def test_fim_encurtado_cobre_so_o_trecho_perdido():
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(soldo, {'data_fim': date(2025, 1, 31)})

    assert janela == (date(2025, 1, 31), date(2025, 3, 31))


def test_reabrir_vigencia_gera_janela_aberta():
    """`data_fim` X → NULL: tudo a partir de X muda de soldo.

    Este é o caso que a versão anterior errava: ela calculava
    `fim = max(fins)` e parava em X, deixando as missões posteriores com o
    custo do soldo seguinte (que passou a não valer mais).
    """
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(soldo, {'data_fim': None})

    assert janela == (date(2025, 3, 31), None)


def test_fechar_vigencia_aberta_gera_janela_aberta():
    """NULL → X: as missões depois de X passam a valer outro soldo.

    Simétrico ao caso acima — não há um "fim" conhecido para limitar a
    janela pela direita.
    """
    soldo = _soldo(date(2019, 1, 1), None)

    janela = _janela_recalculo(soldo, {'data_fim': date(2025, 3, 31)})

    assert janela == (date(2025, 3, 31), None)


def test_inicio_adiantado_cobre_so_o_trecho_novo():
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(soldo, {'data_inicio': date(2018, 6, 1)})

    assert janela == (date(2018, 6, 1), date(2019, 1, 1))


def test_inicio_e_fim_juntos_cobrem_os_dois_trechos():
    """Dois trechos disjuntos viram uma janela só.

    Perde-se o miolo intocado (2019→2025 aqui), mas a alternativa —
    recalcular duas faixas — custaria duas varreduras. Cobrir a mais nunca
    produz custo errado, só trabalho extra.
    """
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(
        soldo,
        {'data_inicio': date(2018, 6, 1), 'data_fim': date(2025, 4, 30)},
    )

    assert janela == (date(2018, 6, 1), date(2025, 4, 30))


def test_valor_tem_precedencia_sobre_datas():
    """Mudou valor E datas: a vigência inteira precisa ser recalculada.

    Não adianta olhar só o delta das datas — o miolo também trocou de
    valor.
    """
    soldo = _soldo(date(2019, 1, 1), date(2025, 3, 31))

    janela = _janela_recalculo(
        soldo,
        {'valor': Decimal('5000.00'), 'data_fim': date(2025, 4, 30)},
    )

    assert janela == (date(2019, 1, 1), date(2025, 4, 30))
