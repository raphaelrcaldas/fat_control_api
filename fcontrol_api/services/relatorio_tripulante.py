"""Consulta comum de etapas para os relatórios individuais."""

from datetime import date

from sqlalchemy import Select, select
from sqlalchemy import func as sql_func

from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TripEtapa,
)
from fcontrol_api.models.shared.aeronaves import Aeronave, ProjetoAnv
from fcontrol_api.models.shared.funcoes import Funcao, FuncaoUae


def consultar_etapas(
    trip_id: int,
    org: str,
    fim: date,
    inicio: date | None = None,
    *,
    vinculos: bool = True,
    detalhes: bool = False,
) -> Select:
    """Regimes agregados por etapa, escopo por missão e funções exercidas.

    Sem vínculos, cada etapa ocorre uma só vez, inclusive com tripulação
    histórica duplicada. Esse modo permite acumular o histórico em SQL.
    """
    filtros = [
        Missao.uae == org,
        Etapa.data <= fim,
        Etapa.id.in_(
            select(TripEtapa.etapa_id).where(TripEtapa.trip_id == trip_id)
        ),
    ]
    if inicio is not None:
        filtros.append(Etapa.data >= inicio)
    regimes = (
        select(
            OIEtapa.etapa_id,
            sql_func
            .sum(OIEtapa.tvoo)
            .filter(OIEtapa.reg == 'd')
            .label('diurno'),
            sql_func
            .sum(OIEtapa.tvoo)
            .filter(OIEtapa.reg == 'n')
            .label('noturno'),
            sql_func.sum(OIEtapa.tvoo).filter(OIEtapa.reg == 'v').label('nvg'),
        )
        .join(Etapa, Etapa.id == OIEtapa.etapa_id)
        .join(Missao, Missao.id == Etapa.missao_id)
        .where(*filtros)
        .group_by(OIEtapa.etapa_id)
        .subquery()
    )
    consulta = (
        select(
            Etapa.id,
            Etapa.data,
            Etapa.tvoo,
            Etapa.pousos,
            Missao.is_simulador,
            ProjetoAnv.modelo,
            sql_func.coalesce(regimes.c.diurno, 0).label('diurno'),
            sql_func.coalesce(regimes.c.noturno, 0).label('noturno'),
            sql_func.coalesce(regimes.c.nvg, 0).label('nvg'),
        )
        .select_from(Etapa)
        .join(Missao, Missao.id == Etapa.missao_id)
        .join(Aeronave, Aeronave.matricula == Etapa.anv)
        .join(ProjetoAnv, ProjetoAnv.id_projeto == Aeronave.projeto)
        .outerjoin(regimes, regimes.c.etapa_id == Etapa.id)
        .where(*filtros)
    )
    if vinculos:
        consulta = (
            consulta
            .join(
                TripEtapa,
                (TripEtapa.etapa_id == Etapa.id)
                & (TripEtapa.trip_id == trip_id),
            )
            .outerjoin(Funcao, Funcao.cod == TripEtapa.func)
            .outerjoin(
                FuncaoUae,
                (FuncaoUae.func_cod == TripEtapa.func)
                & (FuncaoUae.uae == org),
            )
            .add_columns(
                TripEtapa.func,
                sql_func.coalesce(
                    FuncaoUae.nome_custom, Funcao.nome, TripEtapa.func
                ).label('nome'),
            )
            .distinct()
        )
    if detalhes:
        consulta = consulta.add_columns(
            Etapa.missao_id,
            Missao.titulo.label('missao'),
            Etapa.anv,
            Etapa.origem,
            Etapa.destino,
            Etapa.dep,
            Etapa.arr,
            TripEtapa.func_bordo,
        )
    return consulta
