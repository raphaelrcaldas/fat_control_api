"""Schemas Pydantic para Ordem de Missão (OM)"""

from datetime import date, datetime
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from fcontrol_api.schemas.etiquetas import EtiquetaSchema


# --- Campo Especial (usado como JSONB) ---
class CampoEspecial(BaseModel):
    label: str
    valor: str


# --- Etapa ---
class EtapaBase(BaseModel):
    dt_dep: Annotated[datetime, Body()]
    origem: str
    dest: str
    dt_arr: Annotated[datetime, Body()]
    alternativa: str
    tvoo_alt: int  # duração em minutos (estimativa para alternativa)
    qtd_comb: int
    esf_aer: str

    @field_validator('dt_dep', 'dt_arr')
    @classmethod
    def minutos_multiplos_de_5(cls, v: datetime) -> datetime:
        if v.minute % 5 != 0:
            raise ValueError(
                f'Os minutos devem ser múltiplos de 5 (recebido: {v.minute})'
            )
        return v

    @field_validator('tvoo_alt')
    @classmethod
    def tvoo_minimo_5_minutos(cls, v: int) -> int:
        if v < 5:
            raise ValueError('Tempo de voo mínimo é 5 minutos')
        return v

    @model_validator(mode='after')
    def dt_arr_maior_que_dt_dep(self) -> 'EtapaBase':
        if self.dt_arr <= self.dt_dep:
            raise ValueError(
                'Data/hora de chegada deve ser posterior à decolagem'
            )
        # Valida tvoo_etp calculado (dt_arr - dt_dep) >= 5 minutos
        tvoo_etp = int((self.dt_arr - self.dt_dep).total_seconds() / 60)
        if tvoo_etp < 5:
            raise ValueError(
                'Tempo de voo da etapa deve ser no mínimo 5 minutos '
                f'(calculado: {tvoo_etp})'
            )
        return self


class EtapaCreate(EtapaBase):
    pass


class EtapaOut(EtapaBase):
    id: int
    ordem_id: int
    tvoo_etp: int  # calculado: dt_arr - dt_dep em minutos
    model_config = ConfigDict(from_attributes=True)


class EtapaListItem(BaseModel):
    """Schema simplificado de etapa para listagem de ordens"""

    dt_dep: Annotated[datetime, Body()]
    origem: str
    dest: str
    model_config = ConfigDict(from_attributes=True)


# --- Tripulação ---
class TripulacaoOrdemCreate(BaseModel):
    tripulante_id: int
    funcao: str  # pil, mc, lm, tf, oe, os


class TripulanteInfo(BaseModel):
    """Info básica do tripulante para exibição"""

    id: int
    trig: str
    p_g: str
    nome_guerra: str
    model_config = ConfigDict(from_attributes=True)


class TripulacaoOrdemOut(BaseModel):
    id: int
    tripulante_id: int
    funcao: str
    p_g: str  # Snapshot do posto/graduacao no momento da criacao da OM
    tripulante: TripulanteInfo | None = None
    model_config = ConfigDict(from_attributes=True)


# --- Tripulação agrupada por função (formato do frontend) ---
class TripulacaoAgrupada(BaseModel):
    pil: list[int] = []
    mc: list[int] = []
    lm: list[int] = []
    tf: list[int] = []
    oe: list[int] = []
    os: list[int] = []


# --- Ordem de Missão ---
class OrdemMissaoBase(BaseModel):
    numero: str
    matricula_anv: int
    tipo: str
    projeto: str
    status: str
    campos_especiais: list[CampoEspecial] = []
    doc_ref: str | None = None
    data_saida: date | None = None
    uae: str


class OrdemMissaoCreate(OrdemMissaoBase):
    etapas: list[EtapaCreate] = []
    tripulacao: TripulacaoAgrupada | None = None
    etiquetas_ids: list[int] = []


class OrdemMissaoUpdate(BaseModel):
    numero: str | None = None
    matricula_anv: int | None = None
    tipo: str | None = None
    doc_ref: str | None = None
    projeto: str | None = None
    status: str | None = None
    campos_especiais: list[CampoEspecial] | None = None
    etapas: list[EtapaCreate] | None = None
    tripulacao: TripulacaoAgrupada | None = None
    etiquetas_ids: list[int] | None = None
    uae: str | None = None


class OrdemMissaoOut(OrdemMissaoBase):
    id: int
    created_by: int
    created_at: Annotated[datetime, Body()]
    updated_at: Annotated[datetime | None, Body()] = None
    deleted_at: Annotated[datetime | None, Body()] = None
    etapas: list[EtapaOut] = []
    tripulacao: list[TripulacaoOrdemOut] = []
    etiquetas: list[EtiquetaSchema] = []
    model_config = ConfigDict(from_attributes=True)


class OrdemMissaoList(BaseModel):
    """Schema simplificado para listagem"""

    id: int
    numero: str
    matricula_anv: int
    tipo: str
    projeto: str
    status: str
    created_at: Annotated[datetime, Body()]
    doc_ref: str | None = None
    data_saida: date | None = None
    uae: str
    etapas: list[EtapaListItem] = []
    etiquetas: list[EtiquetaSchema] = []
    model_config = ConfigDict(from_attributes=True)
