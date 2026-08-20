from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.instrucao.subprogramas import SubprogramaOut

# Situacao do plano. E informativa: 'encerrado' nao trava edicao, porque
# correcao de plano fechado e rotina (erro de matricula descoberto depois).
StatusPaop = Literal['rascunho', 'vigente', 'encerrado']


class PaopCreate(BaseModel):
    ano: int = Field(ge=2000, le=2100)
    # Sem datas o plano assume o ano civil — o caso comum.
    data_ini: date | None = None
    data_fim: date | None = None
    status: StatusPaop = 'rascunho'


class PaopUpdate(BaseModel):
    """`ano` nao entra: e a identidade do plano (uq uae+ano).

    A coerencia da janela e checada na rota, e nao aqui, para dar a mesma
    resposta do POST — onde as datas podem vir do ano civil e por isso so
    existem depois de derivadas.
    """

    data_ini: date
    data_fim: date
    status: StatusPaop


class PaopResumo(BaseModel):
    """Linha da listagem: cabecalho mais o tamanho do plano."""

    id: int
    ano: int
    data_ini: date
    data_fim: date
    status: StatusPaop
    total_subprogramas: int
    total_matriculas: int


class TripulanteMatriculadoOut(BaseModel):
    """Tripulante matriculado — `id` e o do vinculo, nao o do tripulante."""

    id: int
    trip_id: int
    trig: str
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    data_inclusao: date


class PaopSubprogramaOut(BaseModel):
    id: int
    subprograma: SubprogramaOut
    tripulantes: list[TripulanteMatriculadoOut]


class PaopOut(BaseModel):
    id: int
    ano: int
    data_ini: date
    data_fim: date
    status: StatusPaop
    subprogramas: list[PaopSubprogramaOut]

    model_config = ConfigDict(from_attributes=True)


class PaopSubprogramasSet(BaseModel):
    """Conjunto de subprogramas do plano — a rota reconcilia."""

    subprograma_ids: list[int]


class PaopTripulantesSet(BaseModel):
    """Conjunto de matriculados no item — a rota reconcilia."""

    trip_ids: list[int]
