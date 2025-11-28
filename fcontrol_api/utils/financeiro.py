from datetime import date

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.public.posto_grad import Soldo
from fcontrol_api.schemas.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.utils.datas import listar_datas_entre


def _buscar_valor_por_dia(
    grupo_pg: int, grupo_cidade: int, data: date, cache: dict
) -> float:
    lista: list[DiariaValor] = cache.get((grupo_pg, grupo_cidade), [])

    for item in lista:
        if item.data_inicio <= data and (
            item.data_fim is None or data <= item.data_fim
        ):
            return item.valor
    return 0.0


def _buscar_soldo_por_dia(pg: str, data: date, cache: dict) -> float:
    lista: list[Soldo] = cache.get(pg, [])

    for item in lista:
        if item.data_inicio <= data and (
            item.data_fim is None or data <= item.data_fim
        ):
            return item.valor
    return 0.0


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
    custo = {'subtotal': 0, 'ac_desloc': 0, 'vals': [], 'dias': 0}
    val_ag: dict = {}

    dias_validos = listar_datas_entre(ini, fim)

    for dia in dias_validos[:-1]:
        if sit == 'g':
            valor_dia = _buscar_soldo_por_dia(pg, dia, soldos_cache) * 0.02
        else:
            valor_dia = _buscar_valor_por_dia(gp_pg, gp_cid, dia, vals_cache)

        key = round(valor_dia, 2)
        if key not in val_ag:
            val_ag[key] = {'valor': valor_dia, 'qtd': 0}

        val_ag[key]['qtd'] += 1
        custo['subtotal'] += valor_dia
        custo['dias'] += 1

    if sit != 'g':
        ult_dia = dias_validos[-1]
        if meia_diaria:
            valor_ultimo = _buscar_valor_por_dia(
                gp_pg, gp_cid, ult_dia, vals_cache
            )
            key_last = round(valor_ultimo, 2)
            if key_last not in val_ag:
                val_ag[key_last] = {'valor': valor_ultimo, 'qtd': 0}

            custo['subtotal'] += valor_ultimo * 0.5
            val_ag[key_last]['qtd'] += 0.5
            custo['dias'] += 1

        if ac_desloc:
            custo['ac_desloc'] = 95
            custo['subtotal'] += custo['ac_desloc']

    custo['vals'] = list(val_ag.values())

    return custo


def custo_missao(p_g: str, sit: str, mis: dict) -> dict:
    """
    Lê custos do JSONB pré-calculado e monta estrutura para o frontend.

    Se o JSONB estiver vazio, retorna valores zerados (missão sem custos).
    """
    custos_jsonb = mis.get('custos', {})

    # Se não tem custos, retorna zeros
    if not custos_jsonb or not isinstance(custos_jsonb, dict):
        mis['dias'] = 0
        mis['diarias'] = 0
        mis['valor_total'] = 0
        mis['qtd_ac'] = 0
        return mis

    chave_pg_sit = f'pg_{p_g}_sit_{sit}'

    # Extrair totais gerais
    mis['dias'] = custos_jsonb.get('total_dias', 0)
    mis['diarias'] = custos_jsonb.get('total_diarias', 0)
    acrec_desloc = custos_jsonb.get('acrec_desloc_missao', 0)
    mis['qtd_ac'] = 1 if acrec_desloc > 0 else 0

    # Extrair total de valor para este pg+sit
    totais_pg_sit = custos_jsonb.get('totais_pg_sit', {})
    total_valor = totais_pg_sit.get(chave_pg_sit, {}).get('total_valor', 0)
    mis['valor_total'] = total_valor

    # Popular custos de cada pernoite
    for pnt in mis.get('pernoites', []):
        pernoite_key = f'pernoite_{pnt["id"]}'
        pernoite_custos = custos_jsonb.get(pernoite_key, {})

        # Grupo da cidade
        pnt['gp_cid'] = pernoite_custos.get('grupo_cid', 3)

        # Custos específicos para este pg+sit
        pg_sit_custos = pernoite_custos.get(chave_pg_sit, {})

        # Montar estrutura de custo compatível
        pnt['custo'] = {
            'subtotal': pg_sit_custos.get('subtotal', 0),
            'ac_desloc': pernoite_custos.get('ac_desloc', 0),
            'vals': pg_sit_custos.get('vals', []),
            'dias': pernoite_custos.get('dias', 0),
        }

        # Contar acréscimos de deslocamento
        if pernoite_custos.get('ac_desloc', 0) > 0:
            mis['qtd_ac'] += 1

    return mis


def verificar_modulo(missoes: list[dict]) -> bool:
    """Recebe uma lista de missões e verifica
    se houve um afastamento maior que 15 dias
    em alguma delas.
    """
    DIAS_MODULO = 15

    datas: list[date] = []
    for m in missoes:
        datas_missao = listar_datas_entre(
            m['afast'].date(), m['regres'].date()
        )
        datas.extend(datas_missao)
    datas.sort()

    dias_consec = 1
    for i, _ in enumerate(datas):
        anterior = datas[i - 1]
        atual = datas[i]

        dif = (atual - anterior).days

        if dif != 1:
            dias_consec = 1
            continue

        dias_consec += 1

        if dias_consec >= DIAS_MODULO:
            return True

    return False


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
      "acrec_desloc_missao": int
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

        # Calcular dias do pernoite (comum a todos os usuários)
        dias_validos = listar_datas_entre(pnt.data_ini, pnt.data_fim)
        dias_pernoite = len(dias_validos)

        # Inicializar estrutura do pernoite
        custos_jsonb[pernoite_key] = {
            'grupo_cid': grupo_cidade,
            'dias': dias_pernoite,
            'ac_desloc': 95 if pnt.acrec_desloc else 0,
        }

        # 3. Para cada combinação (p_g, sit), calcular custo
        for p_g, sit in combinacoes_pg_sit:
            pg_sit_key = f'pg_{p_g}_sit_{sit}'
            grupo_pg = grupos_pg.get(p_g)

            # Calcular custo do pernoite para este pg+sit
            custo = _custo_pernoite(
                p_g,
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

            # Armazenar custo no pernoite
            custos_jsonb[pernoite_key][pg_sit_key] = {
                'grupo_pg': grupo_pg,
                'vals': custo['vals'],
                'subtotal': custo['subtotal'],
            }

            # Acumular totais por pg+sit
            if pg_sit_key not in totais_pg_sit:
                totais_pg_sit[pg_sit_key] = {'total_valor': 0}

            totais_pg_sit[pg_sit_key]['total_valor'] += custo['subtotal']

        # 4. Acumular totais gerais da missão
        total_dias_missao += dias_pernoite

        # Calcular diárias do pernoite (usando sit != 'g' como referência)
        diarias_pernoite = 0
        for p_g, sit in combinacoes_pg_sit:
            if sit != 'g':
                pg_sit_key = f'pg_{p_g}_sit_{sit}'
                custo_ref = custos_jsonb[pernoite_key][pg_sit_key]
                for val in custo_ref['vals']:
                    diarias_pernoite += val['qtd']
                break
        else:
            # Se todas forem 'g', não conta diárias (só dias)
            diarias_pernoite = 0

        total_diarias_missao += diarias_pernoite

    # 5. Adicionar totais ao JSONB
    custos_jsonb['totais_pg_sit'] = totais_pg_sit
    custos_jsonb['total_dias'] = total_dias_missao
    custos_jsonb['total_diarias'] = total_diarias_missao
    custos_jsonb['acrec_desloc_missao'] = 95 if frag_mis.acrec_desloc else 0

    return custos_jsonb
