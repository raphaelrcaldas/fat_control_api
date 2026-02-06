"""Testes para custo_missao (leitura de JSONB)."""

from fcontrol_api.utils.financeiro import custo_missao


def test_missao_sem_custos():
    """Missão sem custos retorna zeros."""
    mis = {'custos': {}, 'pernoites': []}
    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 0
    assert resultado['diarias'] == 0
    assert resultado['valor_total'] == 0
    assert resultado['qtd_ac'] == 0


def test_missao_com_custos_calculados():
    """Missão com JSONB de custos retorna valores corretos."""
    custos_jsonb = {
        'total_dias': 5,
        'total_diarias': 4.5,
        'acrec_desloc_missao': 95,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 1500.00},
            'pg_cb_sit_c': {'total_valor': 1200.00},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 3,
            'ac_desloc': 0,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 425.00, 'qtd': 2.5}],
                'subtotal': 1062.50,
            },
        },
        'pernoite_2': {
            'grupo_cid': 3,
            'dias': 2,
            'ac_desloc': 95,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 335.00, 'qtd': 2}],
                'subtotal': 670.00,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}, {'id': 2}],
    }

    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 5
    assert resultado['diarias'] == 4.5
    assert resultado['valor_total'] == 1500.00
    assert resultado['qtd_ac'] == 2  # 1 da missão + 1 do pernoite_2

    pnt1 = resultado['pernoites'][0]
    assert pnt1['gp_cid'] == 1
    assert pnt1['custo']['subtotal'] == 1062.50
    assert pnt1['custo']['dias'] == 3

    pnt2 = resultado['pernoites'][1]
    assert pnt2['gp_cid'] == 3
    assert pnt2['custo']['ac_desloc'] == 95


def test_missao_custos_none():
    """Missão com custos None retorna zeros."""
    mis = {'custos': None, 'pernoites': []}
    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 0
    assert resultado['valor_total'] == 0


def test_missao_custos_tipo_invalido():
    """Missão com custos não-dict (ex: string) retorna zeros."""
    mis = {'custos': 'invalido', 'pernoites': []}
    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 0
    assert resultado['diarias'] == 0
    assert resultado['valor_total'] == 0
    assert resultado['qtd_ac'] == 0


def test_missao_sem_chave_custos():
    """Missão sem a chave 'custos' retorna zeros."""
    mis = {'pernoites': []}
    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 0
    assert resultado['valor_total'] == 0


def test_pg_sit_inexistente_no_jsonb():
    """Consulta com pg+sit sem dados no JSONB retorna valor_total 0."""
    custos_jsonb = {
        'total_dias': 3,
        'total_diarias': 2.5,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 850.00},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 2,
            'ac_desloc': 0,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 425.00, 'qtd': 2}],
                'subtotal': 850.00,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}],
    }

    resultado = custo_missao('cb', 'c', mis)

    assert resultado['dias'] == 3
    assert resultado['diarias'] == 2.5
    assert resultado['valor_total'] == 0
    pnt = resultado['pernoites'][0]
    assert pnt['custo']['subtotal'] == 0
    assert pnt['custo']['vals'] == []


def test_missao_gratificacao_leitura_jsonb():
    """Leitura de custos JSONB para gratificação (sit='g')."""
    custos_jsonb = {
        'total_dias': 5,
        'total_diarias': 0,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cp_sit_g': {'total_valor': 997.60},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 5,
            'ac_desloc': 0,
            'pg_cp_sit_g': {
                'grupo_pg': 3,
                'vals': [{'valor': 199.52, 'qtd': 5}],
                'subtotal': 997.60,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}],
    }

    resultado = custo_missao('cp', 'g', mis)

    assert resultado['dias'] == 5
    assert resultado['valor_total'] == 997.60
    assert resultado['qtd_ac'] == 0
    pnt = resultado['pernoites'][0]
    assert pnt['custo']['subtotal'] == 997.60
    assert pnt['custo']['vals'] == [{'valor': 199.52, 'qtd': 5}]
    assert pnt['custo']['dias'] == 5


def test_sem_acrescimo_missao_com_acrescimo_pernoite():
    """Acréscimo apenas em pernoites, sem acréscimo da missão."""
    custos_jsonb = {
        'total_dias': 4,
        'total_diarias': 3.5,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 1420.00},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 2,
            'ac_desloc': 95,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 425.00, 'qtd': 1.5}],
                'subtotal': 732.50,
            },
        },
        'pernoite_2': {
            'grupo_cid': 3,
            'dias': 2,
            'ac_desloc': 95,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 335.00, 'qtd': 2}],
                'subtotal': 765.00,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}, {'id': 2}],
    }

    resultado = custo_missao('cp', 'c', mis)

    assert resultado['qtd_ac'] == 2
    assert resultado['pernoites'][0]['custo']['ac_desloc'] == 95
    assert resultado['pernoites'][1]['custo']['ac_desloc'] == 95


def test_com_acrescimo_missao_sem_acrescimo_pernoite():
    """Acréscimo apenas na missão, sem acréscimo nos pernoites."""
    custos_jsonb = {
        'total_dias': 3,
        'total_diarias': 2,
        'acrec_desloc_missao': 95,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 850.00},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 3,
            'ac_desloc': 0,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 425.00, 'qtd': 2}],
                'subtotal': 850.00,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}],
    }

    resultado = custo_missao('cp', 'c', mis)

    assert resultado['qtd_ac'] == 1


def test_missao_tres_pernoites():
    """Missão com 3 pernoites em cidades de grupos diferentes."""
    custos_jsonb = {
        'total_dias': 9,
        'total_diarias': 7.5,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cl_sit_c': {'total_valor': 3277.50},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 3,
            'ac_desloc': 0,
            'pg_cl_sit_c': {
                'grupo_pg': 2,
                'vals': [{'valor': 510.00, 'qtd': 2}],
                'subtotal': 1020.00,
            },
        },
        'pernoite_2': {
            'grupo_cid': 2,
            'dias': 3,
            'ac_desloc': 0,
            'pg_cl_sit_c': {
                'grupo_pg': 2,
                'vals': [{'valor': 450.00, 'qtd': 2.5}],
                'subtotal': 1125.00,
            },
        },
        'pernoite_3': {
            'grupo_cid': 3,
            'dias': 3,
            'ac_desloc': 95,
            'pg_cl_sit_c': {
                'grupo_pg': 2,
                'vals': [{'valor': 395.00, 'qtd': 3}],
                'subtotal': 1132.50,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}, {'id': 2}, {'id': 3}],
    }

    resultado = custo_missao('cl', 'c', mis)

    assert resultado['dias'] == 9
    assert resultado['diarias'] == 7.5
    assert resultado['valor_total'] == 3277.50
    assert resultado['qtd_ac'] == 1

    assert resultado['pernoites'][0]['gp_cid'] == 1
    assert resultado['pernoites'][0]['custo']['subtotal'] == 1020.00
    assert resultado['pernoites'][1]['gp_cid'] == 2
    assert resultado['pernoites'][1]['custo']['subtotal'] == 1125.00
    assert resultado['pernoites'][2]['gp_cid'] == 3
    assert resultado['pernoites'][2]['custo']['subtotal'] == 1132.50
    assert resultado['pernoites'][2]['custo']['ac_desloc'] == 95


def test_pernoite_sem_dados_no_jsonb():
    """Pernoite referenciado mas ausente no JSONB usa defaults."""
    custos_jsonb = {
        'total_dias': 2,
        'total_diarias': 1,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 335.00},
        },
        'pernoite_1': {
            'grupo_cid': 3,
            'dias': 2,
            'ac_desloc': 0,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 335.00, 'qtd': 1}],
                'subtotal': 335.00,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}, {'id': 2}],
    }

    resultado = custo_missao('cp', 'c', mis)

    pnt1 = resultado['pernoites'][0]
    assert pnt1['gp_cid'] == 3
    assert pnt1['custo']['subtotal'] == 335.00

    pnt2 = resultado['pernoites'][1]
    assert pnt2['gp_cid'] == 3
    assert pnt2['custo']['subtotal'] == 0
    assert pnt2['custo']['ac_desloc'] == 0
    assert pnt2['custo']['vals'] == []
    assert pnt2['custo']['dias'] == 0


def test_dois_usuarios_consulta_separada():
    """Dois pg+sit no JSONB, cada consulta retorna seu valor."""
    custos_jsonb = {
        'total_dias': 3,
        'total_diarias': 2,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 670.00},
            'pg_cb_sit_c': {'total_valor': 560.00},
        },
        'pernoite_1': {
            'grupo_cid': 3,
            'dias': 3,
            'ac_desloc': 0,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 335.00, 'qtd': 2}],
                'subtotal': 670.00,
            },
            'pg_cb_sit_c': {
                'grupo_pg': 4,
                'vals': [{'valor': 280.00, 'qtd': 2}],
                'subtotal': 560.00,
            },
        },
    }

    mis_cp = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}],
    }
    resultado_cp = custo_missao('cp', 'c', mis_cp)
    assert resultado_cp['valor_total'] == 670.00
    assert (
        resultado_cp['pernoites'][0]['custo']['subtotal'] == 670.00
    )

    mis_cb = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}],
    }
    resultado_cb = custo_missao('cb', 'c', mis_cb)
    assert resultado_cb['valor_total'] == 560.00
    assert (
        resultado_cb['pernoites'][0]['custo']['subtotal'] == 560.00
    )


def test_missao_diarias_fracionadas():
    """Missão com total_diarias fracionado (meia-diária)."""
    custos_jsonb = {
        'total_dias': 3,
        'total_diarias': 2.5,
        'acrec_desloc_missao': 95,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 1157.50},
        },
        'pernoite_1': {
            'grupo_cid': 1,
            'dias': 3,
            'ac_desloc': 95,
            'pg_cp_sit_c': {
                'grupo_pg': 3,
                'vals': [{'valor': 425.00, 'qtd': 2.5}],
                'subtotal': 1157.50,
            },
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [{'id': 1}],
    }

    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 3
    assert resultado['diarias'] == 2.5
    assert resultado['valor_total'] == 1157.50
    assert resultado['qtd_ac'] == 2
    pnt = resultado['pernoites'][0]
    assert pnt['custo']['vals'][0]['qtd'] == 2.5


def test_missao_preserva_campos_originais():
    """custo_missao adiciona campos sem remover os originais."""
    custos_jsonb = {
        'total_dias': 2,
        'total_diarias': 1,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            'pg_cp_sit_c': {'total_valor': 335.00},
        },
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [],
        'nome_missao': 'Op Teste',
        'localidade': 'Brasília',
    }

    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 2
    assert resultado['valor_total'] == 335.00
    assert resultado['nome_missao'] == 'Op Teste'
    assert resultado['localidade'] == 'Brasília'


def test_missao_totais_pg_sit_ausente():
    """JSONB sem chave totais_pg_sit retorna valor_total 0."""
    custos_jsonb = {
        'total_dias': 2,
        'total_diarias': 1,
        'acrec_desloc_missao': 0,
    }

    mis = {
        'custos': custos_jsonb,
        'pernoites': [],
    }

    resultado = custo_missao('cp', 'c', mis)

    assert resultado['dias'] == 2
    assert resultado['valor_total'] == 0
