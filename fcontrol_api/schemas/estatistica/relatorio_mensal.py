from datetime import date, time

from pydantic import BaseModel, Field

from fcontrol_api.schemas.estatistica.relatorio_anual import (
    AeronaveFuncaoAnual,
    MetricasAnuais,
    TripulanteRelatorio,
)


class FuncaoEtapaMensal(BaseModel):
    func: str
    nome: str
    func_bordo: str


class EtapaMensal(BaseModel):
    """Uma linha por etapa; tempos em minutos e regimes independentes."""

    id: int
    data: date
    missao_id: int
    missao: str | None = None
    anv: str
    modelo: str
    origem: str
    destino: str
    dep: time
    arr: time
    tvoo: int
    diurno: int
    noturno: int
    nvg: int
    sem_regime: int
    pousos: int
    funcoes: list[FuncaoEtapaMensal] = Field(default_factory=list)


class ResumoMensal(BaseModel):
    """Tempos em minutos; diurno, noturno e NVG são independentes.

    Totais e acumulados terminam no mês consultado, limitados ao dia atual.
    """

    total: MetricasAnuais = Field(
        default_factory=MetricasAnuais,
        description='Totais apenas do mês consultado, até o dia atual.',
    )
    acumulado_ano: MetricasAnuais = Field(
        default_factory=MetricasAnuais,
        description=(
            'Acumulado desde 1º de janeiro até o fim do mês consultado, '
            'limitado ao dia atual.'
        ),
    )
    acumulado_geral: MetricasAnuais = Field(
        default_factory=MetricasAnuais,
        description=(
            'Acumulado de todo o histórico até o fim do mês consultado, '
            'limitado ao dia atual.'
        ),
    )
    por_aeronave_funcao: list[AeronaveFuncaoAnual] = Field(
        default_factory=list
    )
    etapas: list[EtapaMensal] = Field(default_factory=list)


class RelatorioMensal(BaseModel):
    ano: int
    mes: int
    tripulante: TripulanteRelatorio
    aeronaves: ResumoMensal
    simuladores: ResumoMensal
