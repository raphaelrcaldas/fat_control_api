"""Cálculo puro dos custos de uma missão (materialização do cache JSONB).

Funções sem I/O: recebem os inputs validados (schemas) e os caches de
referência já carregados, e produzem o dict `custos` que é gravado em
`FragMis.custos`. O formato desse JSONB está documentado em
`calcular_custos_frag_mis`. A chave canônica pg+sit e o hash de
integridade vêm de `integridade` — fonte única compartilhada com a
leitura (`leitura.custo_missao`).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.shared.posto_grad import Soldo
from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.services.custos.integridade import (
    chave_pg_sit,
    gerar_hash_custos,
)
from fcontrol_api.utils.datas import listar_datas_entre

# Toda a aritmética monetária ocorre em Decimal; a conversão para float
# acontece só no limite de escrita do JSONB (ver calcular_custos_frag_mis).
CENTAVO = Decimal('0.01')


def _q(valor: Decimal) -> Decimal:
    """Quantiza um valor monetário a centavos (ROUND_HALF_UP, padrão BRL)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _buscar_valor_por_dia(
    grupo_pg: int, grupo_cidade: int, data: date, cache: dict
) -> Decimal:
    lista: list[DiariaValor] = cache.get((grupo_pg, grupo_cidade), [])

    for item in lista:
        if item.data_inicio <= data and (
            item.data_fim is None or data <= item.data_fim
        ):
            return item.valor
    return Decimal('0')


def _buscar_soldo_por_dia(pg: str, data: date, cache: dict) -> Decimal:
    lista: list[Soldo] = cache.get(pg, [])

    for item in lista:
        if item.data_inicio <= data and (
            item.data_fim is None or data <= item.data_fim
        ):
            return item.valor
    return Decimal('0')


def _custo_pernoite(
    pg,
    sit,
    ini,
    fim,
    gp_pg,
    gp_cid,
    meia_diaria,
    ac_desloc,
    soldos_cache,
    vals_cache,
):
    custo = {
        'subtotal': Decimal('0'),
        'ac_desloc': 0,
        'vals': [],
        'dias': 0,
    }
    val_ag: dict = {}

    dias_validos = listar_datas_entre(ini, fim)

    # Para gratificação, processa TODOS os dias (2% do soldo por dia)
    # Para diárias normais, processa todos exceto o último (tratado separado)
    if sit == 'g':
        for dia in dias_validos:
            soldo_dia = _buscar_soldo_por_dia(pg, dia, soldos_cache)
            valor_dia = _q(soldo_dia * Decimal('0.02'))

            key = valor_dia
            if key not in val_ag:
                val_ag[key] = {'valor': valor_dia, 'qtd': 0}

            val_ag[key]['qtd'] += 1
            custo['subtotal'] += valor_dia
            custo['dias'] += 1
    else:
        # Diárias normais: processa todos exceto último
        for dia in dias_validos[:-1]:
            valor_dia = _buscar_valor_por_dia(gp_pg, gp_cid, dia, vals_cache)

            key = valor_dia
            if key not in val_ag:
                val_ag[key] = {'valor': valor_dia, 'qtd': 0}

            val_ag[key]['qtd'] += 1
            custo['subtotal'] += valor_dia
            custo['dias'] += 1

        # Último dia: meia-diária opcional + acréscimo deslocamento
        ult_dia = dias_validos[-1]
        if meia_diaria:
            valor_ultimo = _buscar_valor_por_dia(
                gp_pg, gp_cid, ult_dia, vals_cache
            )
            key_last = valor_ultimo
            if key_last not in val_ag:
                val_ag[key_last] = {'valor': valor_ultimo, 'qtd': 0}

            custo['subtotal'] += _q(valor_ultimo * Decimal('0.5'))
            val_ag[key_last]['qtd'] += 0.5
            custo['dias'] += 1

        if ac_desloc:
            custo['ac_desloc'] = 95
            custo['subtotal'] += Decimal('95')

    custo['vals'] = list(val_ag.values())

    return custo


def calcular_custos_frag_mis(
    frag_mis: CustoFragMisInput,
    users_frag: list[CustoUserFragInput],
    pernoites: list[CustoPernoiteInput],
    grupos_pg: dict[str, int],
    grupos_cidade: dict[int, int],
    valores_cache: dict[tuple[int, int], list[DiariaValor]],
    soldos_cache: dict[str, list[Soldo]],
) -> dict:
    """
    Calcula e retorna custos pré-processados para FragMis em formato JSONB.

    Estrutura retornada:
    {
      "pernoite_<id>": {
        "grupo_cid": int,
        "dias": int,
        "ac_desloc": int,
        "pg_<p_g>_sit_<sit>": {
          "grupo_pg": int,
          "vals": [{"valor": float, "qtd": float}],
          "subtotal": float
        }
      },
      "totais_pg_sit": {
        "pg_<p_g>_sit_<sit>": {
          "total_valor": float
        }
      },
      "total_dias": int,
      "total_diarias": float,
      "acrec_desloc_missao": int,
      "_input_hash": str
    }

    Args:
        frag_mis: Dados da missão (validados com Pydantic)
        users_frag: Lista de usuários na missão com p_g e sit (validados)
        pernoites: Lista de pernoites com dados necessários (validados)
        grupos_pg: Cache de mapeamento pg_short -> grupo_pg (número)
        grupos_cidade: Cache de mapeamento cidade_id -> grupo_cidade (número)
        valores_cache: Cache de valores de diárias por (grupo_pg, grupo_cid)
        soldos_cache: Cache de soldos por pg_short

    Returns:
        dict: Estrutura JSONB com custos calculados e validados
    """
    custos_jsonb = {}
    totais_pg_sit = {}
    total_dias_missao = 0
    total_diarias_missao = 0

    # 1. Extrair combinações únicas de (p_g, sit)
    combinacoes_pg_sit = {(uf.p_g, uf.sit) for uf in users_frag}

    # 2. Para cada pernoite, calcular custos
    for pnt in pernoites:
        pernoite_id = pnt.id
        pernoite_key = f'pernoite_{pernoite_id}'

        # Determinar grupo_cidade (acesso direto ao atributo validado)
        cidade_codigo = pnt.cidade_codigo
        grupo_cidade = grupos_cidade.get(cidade_codigo, 3)

        # Inicializar estrutura do pernoite (dias será preenchido após loop)
        custos_jsonb[pernoite_key] = {
            'grupo_cid': grupo_cidade,
            'dias': 0,
            'ac_desloc': 95 if pnt.acrec_desloc else 0,
        }

        # 3. Para cada combinação (p_g, sit), calcular custo
        dias_pernoite = 0
        diarias_pernoite = 0

        for p_g, sit in combinacoes_pg_sit:
            pg_sit_key = chave_pg_sit(p_g, sit)
            grupo_pg = grupos_pg.get(p_g.value)

            # Calcular custo do pernoite para este pg+sit
            custo = _custo_pernoite(
                p_g.value,
                sit,
                pnt.data_ini,
                pnt.data_fim,
                grupo_pg,
                grupo_cidade,
                pnt.meia_diaria,
                pnt.acrec_desloc,
                soldos_cache,
                valores_cache,
            )

            # Armazenar custo no pernoite (float só no limite do JSONB;
            # os valores já estão quantizados a centavos)
            custos_jsonb[pernoite_key][pg_sit_key] = {
                'grupo_pg': grupo_pg,
                'vals': [
                    {'valor': float(v['valor']), 'qtd': v['qtd']}
                    for v in custo['vals']
                ],
                'subtotal': float(custo['subtotal']),
            }

            # Acumular totais por pg+sit (em Decimal até o passo final)
            if pg_sit_key not in totais_pg_sit:
                totais_pg_sit[pg_sit_key] = {'total_valor': Decimal('0')}

            totais_pg_sit[pg_sit_key]['total_valor'] += custo['subtotal']

            # Capturar dias/diárias do primeiro usuário não-gratificação
            if sit != 'g' and dias_pernoite == 0:
                dias_pernoite = custo['dias']
                for val in custo['vals']:
                    diarias_pernoite += val['qtd']

        # Se todos forem gratificação, usar dias do primeiro
        if dias_pernoite == 0 and combinacoes_pg_sit:
            p_g, sit = next(iter(combinacoes_pg_sit))
            pg_sit_key = chave_pg_sit(p_g, sit)
            # Recalcular dias para gratificação (todos os dias)
            dias_pernoite = len(listar_datas_entre(pnt.data_ini, pnt.data_fim))

        # Atualizar dias no pernoite
        custos_jsonb[pernoite_key]['dias'] = dias_pernoite

        # 4. Acumular totais gerais da missão
        total_dias_missao += dias_pernoite
        total_diarias_missao += diarias_pernoite

    # 5. Somar acréscimo de deslocamento da missão aos totais
    acrec_desloc_missao = 95 if frag_mis.acrec_desloc else 0
    if acrec_desloc_missao:
        for totais in totais_pg_sit.values():
            totais['total_valor'] += acrec_desloc_missao

    # 6. Adicionar totais ao JSONB (float só aqui, no limite de escrita)
    custos_jsonb['totais_pg_sit'] = {
        chave: {'total_valor': float(t['total_valor'])}
        for chave, t in totais_pg_sit.items()
    }
    custos_jsonb['total_dias'] = total_dias_missao
    custos_jsonb['total_diarias'] = total_diarias_missao
    custos_jsonb['acrec_desloc_missao'] = acrec_desloc_missao

    # 7. Hash de integridade dos inputs locais (detecção de drift na
    # leitura — ver verificar_integridade_custos)
    custos_jsonb['_input_hash'] = gerar_hash_custos(
        frag_mis, users_frag, pernoites
    )

    return custos_jsonb
