"""Apuracao individual por funcao exercida, sem funcao principal."""

from dataclasses import dataclass
from datetime import date

from fcontrol_api.schemas.estatistica.relatorio_anual import (
    AeronaveFuncaoAnual,
    FuncaoAnual,
    MetricasAnuais,
    ResumoAnual,
)


@dataclass(frozen=True)
class EtapaApurada:
    id: int
    data: date
    tvoo: int
    pousos: int
    is_simulador: bool
    func: str
    nome: str
    modelo: str
    diurno: int
    noturno: int
    nvg: int


def _somar(total: MetricasAnuais, etapa: EtapaApurada) -> None:
    total.tvoo += etapa.tvoo
    total.diurno += etapa.diurno
    total.noturno += etapa.noturno
    total.nvg += etapa.nvg
    total.sem_regime += max(
        etapa.tvoo - etapa.diurno - etapa.noturno - etapa.nvg, 0
    )
    total.pousos += etapa.pousos
    total.etapas += 1
    if total.ultimo_voo is None or etapa.data > total.ultimo_voo:
        total.ultimo_voo = etapa.data


def apurar_resumo(etapas: list[EtapaApurada]) -> ResumoAnual:
    """Uma etapa conta uma vez no total e uma vez em cada funcao exercida.

    Novos lancamentos impedem tripulante repetido na etapa. A deduplicacao
    permanece defensiva para dados historicos, sem reescrever esses vinculos.
    """
    total = MetricasAnuais()
    por_funcao: dict[str, FuncaoAnual] = {}
    por_modelo: dict[tuple[str, str], AeronaveFuncaoAnual] = {}
    vistas: set[int] = set()
    funcoes_vistas: set[tuple[int, str]] = set()

    for etapa in etapas:
        if etapa.id not in vistas:
            _somar(total, etapa)
            vistas.add(etapa.id)
        func_key = (etapa.id, etapa.func)
        if func_key in funcoes_vistas:
            continue
        funcoes_vistas.add(func_key)

        if etapa.func not in por_funcao:
            por_funcao[etapa.func] = FuncaoAnual(
                func=etapa.func,
                nome=etapa.nome,
            )
        _somar(por_funcao[etapa.func], etapa)

        modelo_key = (etapa.modelo, etapa.func)
        if modelo_key not in por_modelo:
            por_modelo[modelo_key] = AeronaveFuncaoAnual(
                modelo=etapa.modelo,
                func=etapa.func,
                nome=etapa.nome,
            )
        _somar(por_modelo[modelo_key], etapa)

    return ResumoAnual(
        total=total,
        por_funcao=sorted(por_funcao.values(), key=lambda r: r.func),
        por_aeronave_funcao=sorted(
            por_modelo.values(),
            key=lambda r: (r.modelo, r.func),
        ),
    )
