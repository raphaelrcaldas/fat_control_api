"""Detalhes do mês e acumulados individuais sem multiplicar vínculos."""

from datetime import date

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.estatistica.etapa import Etapa, TripEtapa
from fcontrol_api.schemas.estatistica.relatorio_anual import MetricasAnuais
from fcontrol_api.schemas.estatistica.relatorio_mensal import (
    EtapaMensal,
    FuncaoEtapaMensal,
    ResumoMensal,
)
from fcontrol_api.services.relatorio_anual import EtapaApurada, apurar_resumo
from fcontrol_api.services.relatorio_tripulante import consultar_etapas


async def consultar_acumulados(
    session: AsyncSession,
    trip_id: int,
    org: str,
    inicio_ano: date,
    fim: date,
) -> dict[bool, dict[str, MetricasAnuais]]:
    """Agrega histórico em SQL; filtros anuais não incluem meses seguintes."""
    base = consultar_etapas(trip_id, org, fim, vinculos=False).subquery()
    sem_regime = sql_func.greatest(
        base.c.tvoo - base.c.diurno - base.c.noturno - base.c.nvg, 0
    )
    campos = {
        'tvoo': base.c.tvoo,
        'diurno': base.c.diurno,
        'noturno': base.c.noturno,
        'nvg': base.c.nvg,
        'sem_regime': sem_regime,
        'pousos': base.c.pousos,
    }
    colunas = []
    for periodo in ('acumulado_ano', 'acumulado_geral'):
        filtro = (
            base.c.data >= inicio_ano if periodo == 'acumulado_ano' else True
        )
        for nome, campo in campos.items():
            colunas.append(
                sql_func.coalesce(sql_func.sum(campo).filter(filtro), 0).label(
                    f'{periodo}_{nome}'
                )
            )
        colunas.extend([
            sql_func
            .count(base.c.id)
            .filter(filtro)
            .label(f'{periodo}_etapas'),
            sql_func
            .max(base.c.data)
            .filter(filtro)
            .label(f'{periodo}_ultimo_voo'),
        ])
    rows = await session.execute(
        select(base.c.is_simulador, *colunas).group_by(base.c.is_simulador)
    )
    acumulados = {}
    for row in rows:
        dados = row._mapping
        acumulados[dados['is_simulador']] = {
            periodo: MetricasAnuais(**{
                nome: dados[f'{periodo}_{nome}']
                for nome in MetricasAnuais.model_fields
            })
            for periodo in ('acumulado_ano', 'acumulado_geral')
        }
    return acumulados


async def apurar_mensal(
    session: AsyncSession,
    trip_id: int,
    org: str,
    inicio: date,
    fim: date,
) -> tuple[ResumoMensal, ResumoMensal]:
    rows = await session.execute(
        consultar_etapas(trip_id, org, fim, inicio, detalhes=True).order_by(
            Etapa.data,
            Etapa.dep,
            Etapa.id,
            TripEtapa.func,
            TripEtapa.func_bordo,
        )
    )
    etapas_apuradas: dict[bool, list[EtapaApurada]] = {False: [], True: []}
    detalhes: dict[bool, dict[int, EtapaMensal]] = {False: {}, True: {}}
    funcoes_vistas: set[tuple[int, str, str]] = set()
    for row in rows:
        dados = row._mapping
        simulador = dados['is_simulador']
        etapas_apuradas[simulador].append(
            EtapaApurada(**{
                nome: dados[nome] for nome in EtapaApurada.__dataclass_fields__
            })
        )
        etapa_id = dados['id']
        if etapa_id not in detalhes[simulador]:
            detalhes[simulador][etapa_id] = EtapaMensal(
                **{
                    nome: dados[nome]
                    for nome in EtapaMensal.model_fields
                    if nome not in {'sem_regime', 'funcoes'}
                },
                sem_regime=max(
                    dados['tvoo']
                    - dados['diurno']
                    - dados['noturno']
                    - dados['nvg'],
                    0,
                ),
            )
        chave = (etapa_id, dados['func'], dados['func_bordo'])
        if chave not in funcoes_vistas:
            detalhes[simulador][etapa_id].funcoes.append(
                FuncaoEtapaMensal(
                    func=dados['func'],
                    nome=dados['nome'],
                    func_bordo=dados['func_bordo'],
                )
            )
            funcoes_vistas.add(chave)
    acumulados = await consultar_acumulados(
        session, trip_id, org, date(inicio.year, 1, 1), fim
    )
    resumos = []
    for simulador in (False, True):
        resumo = apurar_resumo(etapas_apuradas[simulador])
        resumos.append(
            ResumoMensal(
                total=resumo.total,
                por_aeronave_funcao=resumo.por_aeronave_funcao,
                etapas=list(detalhes[simulador].values()),
                **acumulados.get(simulador, {}),
            )
        )
    return resumos[0], resumos[1]
