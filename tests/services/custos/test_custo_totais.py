"""Testes de `custo_totais` — parte pura da leitura do JSONB.

Existe para que o cache do comissionamento leia os agregados sem carregar
e serializar a missão inteira. O risco que estes testes cobrem é os dois
caminhos divergirem com o tempo: `custo_missao` é quem alimenta as telas,
`custo_totais` é quem alimenta o dinheiro acumulado do comissionamento —
os dois têm de concordar sempre.
"""

import pytest

from fcontrol_api.services.custos.leitura import custo_missao, custo_totais

AGREGADOS = ('dias', 'diarias', 'valor_total')

# JSONB de uma missão de 3 dias em grupo 1, com um comissionado e um
# gratificado — o bastante para exercitar chave presente, chave ausente e
# acréscimo de deslocamento.
CUSTOS = {
    'pernoite_1': {
        'grupo_cid': 1,
        'dias': 3,
        'ac_desloc': 95,
        'pg_cp_sit_c': {
            'grupo_pg': 3,
            'vals': [{'valor': 425.0, 'qtd': 3}],
            'subtotal': 1275.0,
        },
    },
    'totais_pg_sit': {
        'pg_cp_sit_c': {'total_valor': 1275.0},
        'pg_cb_sit_g': {'total_valor': 172.14},
    },
    'total_dias': 3,
    'total_diarias': 3,
    'acrec_desloc_missao': 95,
}


@pytest.mark.parametrize(
    ('p_g', 'sit'),
    [
        ('cp', 'c'),  # chave presente
        ('cb', 'g'),  # outra chave presente
        ('br', 'c'),  # chave ausente -> zerado + inconsistente
    ],
)
def test_concorda_com_custo_missao_nos_agregados(p_g, sit):
    """Os dois caminhos leem o mesmo JSONB e chegam ao mesmo total."""
    mis = {
        'id': 1,
        'n_doc': '001',
        'custos': CUSTOS,
        'pernoites': [{'id': 1}],
    }

    pela_missao = custo_missao(p_g, sit, mis)
    pelos_totais = custo_totais(
        p_g, sit, CUSTOS, tem_pernoites=True, missao_id=1, n_doc='001'
    )

    for campo in AGREGADOS:
        assert pelos_totais[campo] == pela_missao[campo]

    assert pelos_totais['custo_inconsistente'] == pela_missao.get(
        'custo_inconsistente', False
    )


def test_cache_vazio_sem_pernoites_nao_sinaliza():
    """Missão sem pernoites não tem custo a materializar — é esperado."""
    totais = custo_totais('cp', 'c', {}, tem_pernoites=False)

    assert totais['custo_inconsistente'] is False
    assert all(totais[c] == 0 for c in AGREGADOS)


def test_cache_vazio_com_pernoites_sinaliza():
    """Recálculo pendente: zera os valores e levanta a bandeira.

    Regra de segurança do domínio — melhor sinalizar do que devolver
    dinheiro errado em silêncio.
    """
    totais = custo_totais('cp', 'c', {}, tem_pernoites=True)

    assert totais['custo_inconsistente'] is True
    assert all(totais[c] == 0 for c in AGREGADOS)


def test_cache_none_com_pernoites_sinaliza():
    totais = custo_totais('cp', 'c', None, tem_pernoites=True)

    assert totais['custo_inconsistente'] is True


def test_chave_pg_sit_ausente_zera_so_o_valor():
    """Drift de pg+sit: `valor_total` zera, mas dias/diárias continuam.

    `total_dias` e `total_diarias` são da missão, não da combinação — o
    que se perde é o valor daquele militar.
    """
    totais = custo_totais('br', 'c', CUSTOS, tem_pernoites=True)

    assert totais['custo_inconsistente'] is True
    assert totais['valor_total'] == 0
    assert totais['dias'] == 3
    assert totais['diarias'] == 3


def test_qtd_ac_conta_so_o_acrescimo_da_missao():
    """O dos pernoites é somado por `custo_missao`, que os tem em mãos.

    Aqui o JSONB traz acréscimo na missão E no pernoite: `custo_totais`
    conta 1, `custo_missao` conta 2.
    """
    mis = {'id': 1, 'n_doc': '001', 'custos': CUSTOS, 'pernoites': [{'id': 1}]}

    assert custo_totais('cp', 'c', CUSTOS, tem_pernoites=True)['qtd_ac'] == 1
    assert custo_missao('cp', 'c', mis)['qtd_ac'] == 2
