from datetime import date

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.public.posto_grad import Soldo
from fcontrol_api.utils.datas import listar_datas_entre


def buscar_valor_por_dia(
    grupo_pg: int, grupo_cidade: int, data: date, cache: dict
) -> float:
    lista: list[DiariaValor] = cache.get((grupo_pg, grupo_cidade), [])

    for item in lista:
        if item.data_inicio <= data and (
            item.data_fim is None or data <= item.data_fim
        ):
            return item.valor
    return 0.0


def buscar_soldo_por_dia(pg: str, data: date, cache: dict) -> float:
    lista: list[Soldo] = cache.get(pg, [])

    for item in lista:
        if item.data_inicio <= data and (
            item.data_fim is None or data <= item.data_fim
        ):
            return item.valor
    return 0.0


def custo_pernoite(
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

    # Se sit == 'g', não interagir com o último dia: iteramos até penúltimo
    iter_dias = dias_validos[:-1] if sit == 'g' else dias_validos
    for dia in iter_dias:
        if sit == 'g':
            valor_dia = buscar_soldo_por_dia(pg, dia, soldos_cache) * 0.02
        else:
            valor_dia = buscar_valor_por_dia(gp_pg, gp_cid, dia, vals_cache)

        key = round(valor_dia, 2)
        if key not in val_ag:
            val_ag[key] = {'valor': valor_dia, 'qtd': 0}

        val_ag[key]['qtd'] += 1
        custo['subtotal'] += valor_dia
        custo['dias'] += 1

    if sit != 'g':
        ult_dia = dias_validos[-1]
        if meia_diaria:
            valor_ultimo = buscar_valor_por_dia(
                gp_pg, gp_cid, ult_dia, vals_cache
            )
            key_last = round(valor_ultimo, 2)
            custo['subtotal'] -= valor_ultimo * 0.5
            val_ag[key_last]['qtd'] -= 0.5

        if ac_desloc:
            custo['ac_desloc'] = 95
            custo['subtotal'] += custo['ac_desloc']

    custo['vals'] = list(val_ag.values())

    return custo


def custo_missao(
    p_g: str,
    sit: str,
    mis: dict,
    grupos_pg: dict,
    grupos_cidade: dict,
    valores_cache: dict,
    soldos_cache: dict = None,
) -> dict:
    """
    Modifica o dicionário da missão adicionando os custos calculados
    com base nos pernoites.
    """
    grupo_pg = grupos_pg.get(p_g)

    mis['dias'] = 0
    mis['diarias'] = 0
    mis['valor_total'] = 0
    mis['qtd_ac'] = 0

    for pnt in mis['pernoites']:
        grupo_cidade = grupos_cidade.get(pnt['cidade']['codigo'], 3)
        pnt['gp_cid'] = grupo_cidade

        custo = custo_pernoite(
            p_g,
            sit,
            pnt['data_ini'],
            pnt['data_fim'],
            grupo_pg,
            grupo_cidade,
            pnt['meia_diaria'],
            pnt['acrec_desloc'],
            soldos_cache,
            valores_cache,
        )

        pnt['custo'] = custo

        if pnt['acrec_desloc']:
            mis['qtd_ac'] += 1

        if sit != 'g':
            for val in custo['vals']:
                mis['diarias'] += val['qtd']

        mis['valor_total'] += custo['subtotal']
        mis['dias'] += custo['dias']

    return mis


def verificar_modulo(missoes: list[dict]) -> bool:
    """Recebe uma lista de missões e verifica
    se houve um afastamento maior que 15 dias
    em alguma delas.
    """
    DIAS_MODULO = 15

    datas: list[date] = []
    for m in missoes:
        datas_missao = listar_datas_entre(m['afast'], m['regres'])
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
