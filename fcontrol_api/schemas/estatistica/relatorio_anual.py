from datetime import date

from pydantic import BaseModel, Field


class MetricasAnuais(BaseModel):
    """Tempos em minutos. Diurno, noturno e NVG sao regimes independentes."""

    tvoo: int = 0
    diurno: int = 0
    noturno: int = 0
    nvg: int = 0
    sem_regime: int = 0
    pousos: int = 0
    etapas: int = 0
    ultimo_voo: date | None = None


class FuncaoAnual(MetricasAnuais):
    func: str
    nome: str


class AeronaveFuncaoAnual(FuncaoAnual):
    modelo: str


class ResumoAnual(BaseModel):
    total: MetricasAnuais = Field(default_factory=MetricasAnuais)
    por_funcao: list[FuncaoAnual] = Field(default_factory=list)
    por_aeronave_funcao: list[AeronaveFuncaoAnual] = Field(
        default_factory=list
    )


class TripulanteRelatorio(BaseModel):
    """Identificacao sem funcao de cadastro ou operacionalidade."""

    id: int
    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None = None
    trig: str


class RelatorioAnual(BaseModel):
    ano: int
    tripulante: TripulanteRelatorio
    aeronaves: ResumoAnual
    simuladores: ResumoAnual
