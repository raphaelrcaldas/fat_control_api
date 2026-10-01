"""Critérios SQL da listagem, aplicados antes de qualquer paginação."""

from typing import Literal

from sqlalchemy import case, func

from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.comiss import ComissOrderBy

# Paridade com client/src/app/(home)/cegep/comiss/comissDerivacoes.ts e
# components/detail/metricas.ts (DIARIA_MINIMA) do mesmo diretório: dias
# estimados do comparativo usam a referência fixa de 335, não a diária vigente
# de cada militar. O comissDerivacoes.ts do FatBird é outro, com regra própria.
DIARIA_MINIMA = 335


def ordenar_comiss(
    query,
    order_by: ComissOrderBy | None,
    direction: Literal['asc', 'desc'],
):
    """Mantém a leitura legada por abertura quando não há ordem explícita."""
    if order_by is None:
        return query.order_by(
            Comissionamento.data_ab.desc(), Comissionamento.id.asc()
        )

    if order_by == 'militar':
        query = query.join(PostoGrad, User.p_g == PostoGrad.short)
        # O comparador do Client trata promoção ausente como '' e ant_rel
        # ausente como zero: vêm antes em ASC, depois em DESC.
        columns = [
            PostoGrad.ant,
            User.ult_promo,
            func.coalesce(User.ant_rel, 0),
        ]
        clauses = [
            column.asc().nulls_first()
            if direction == 'asc'
            else column.desc().nulls_last()
            for column in columns
        ]
    else:
        cache = Comissionamento.cache_calc
        periodo = Comissionamento.dias_cumprir.isnot(None) & (
            Comissionamento.dias_cumprir != 0
        )
        previsto = case(
            (periodo, Comissionamento.dias_cumprir),
            else_=(Comissionamento.valor_aj_ab + Comissionamento.valor_aj_fc)
            / DIARIA_MINIMA,
        )
        computado = case(
            (periodo, func.coalesce(cache['dias_comp'].as_float(), 0)),
            else_=func.coalesce(cache['vals_comp'].as_float(), 0)
            / DIARIA_MINIMA,
        )
        columns = {
            'data_ab': Comissionamento.data_ab,
            'data_fc': Comissionamento.data_fc,
            'tipo': case((periodo, 1), else_=0),
            'completude': func.coalesce(cache['completude'].as_float(), 0),
            'modulo': func.coalesce(cache['modulo'].as_boolean(), False),
            'previsto': previsto,
            'computado': computado,
            'restante': previsto - computado,
        }
        column = columns[order_by]
        clauses = [
            column.asc().nulls_last()
            if direction == 'asc'
            else column.desc().nulls_last()
        ]

    return query.order_by(*clauses, Comissionamento.id.asc())
