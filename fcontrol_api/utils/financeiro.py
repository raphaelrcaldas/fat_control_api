from datetime import date

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.cegep.missoes import PernoiteFrag
from fcontrol_api.models.public.posto_grad import Soldo


def qtd_dias_pnt(pernoite: PernoiteFrag) -> float:
    if not pernoite.data_ini or not pernoite.data_fim:
        return 0.0

    data_ini = pernoite.data_ini.date()
    data_fim = pernoite.data_fim.date()
    dias = max((data_fim - data_ini).days, 0)

    if pernoite.meia_diaria:
        dias += 0.5

    return dias


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
