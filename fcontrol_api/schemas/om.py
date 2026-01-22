"""Schemas Pydantic para Ordem de Missão (OM)"""

from datetime import date, datetime
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.etiquetas import EtiquetaSchema
from fcontrol_api.schemas.tripulantes import TripBasicInfo

# Constantes de validação
TVOO_MINIMO = 5  # Tempo mínimo de voo em minutos
ICAO_CODE_LENGTH = 4  # Código ICAO de aeródromo


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
        if v < TVOO_MINIMO:
            raise ValueError(f'Tempo de voo mínimo é {TVOO_MINIMO} minutos')
        return v

    @model_validator(mode='after')
    def dt_arr_maior_que_dt_dep(self) -> 'EtapaBase':
        if self.dt_arr <= self.dt_dep:
            raise ValueError(
                'Data/hora de chegada deve ser posterior à decolagem'
            )
        # Valida tvoo_etp calculado (dt_arr - dt_dep) >= TVOO_MINIMO
        tvoo_etp = int((self.dt_arr - self.dt_dep).total_seconds() / 60)
        if tvoo_etp < TVOO_MINIMO:
            raise ValueError(
                f'Tempo de voo da etapa deve ser no mínimo {TVOO_MINIMO} min '
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


class TripulacaoOrdemOut(BaseModel):
    id: int
    tripulante_id: int
    funcao: str
    # Snapshot do posto/graduacao no momento da criacao da OM
    p_g: PostoGradEnum
    tripulante: TripBasicInfo | None = None
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
# Core: campos essenciais compartilhados entre todos os schemas
class OrdemMissaoCore(BaseModel):
    """Campos essenciais de uma Ordem de Missão"""

    matricula_anv: int
    tipo: str
    projeto: str
    status: str
    doc_ref: str | None = None
    data_saida: date | None = None
    uae: str
    esf_aer: int = 0


# --- INPUT: Schemas de entrada (frontend → backend) ---
class OrdemMissaoCreate(OrdemMissaoCore):
    """Criação de OM - numero será gerado pelo backend"""

    campos_especiais: list[CampoEspecial] = []
    etapas: list[EtapaCreate] = []
    tripulacao: TripulacaoAgrupada | None = None
    etiquetas_ids: list[int] = []


class OrdemMissaoUpdate(BaseModel):
    """Atualização parcial de OM - todos campos opcionais"""

    numero: str | None = None
    matricula_anv: int | None = None
    tipo: str | None = None
    projeto: str | None = None
    status: str | None = None
    doc_ref: str | None = None
    data_saida: date | None = None
    uae: str | None = None
    esf_aer: int | None = None
    campos_especiais: list[CampoEspecial] | None = None
    etapas: list[EtapaCreate] | None = None
    tripulacao: TripulacaoAgrupada | None = None
    etiquetas_ids: list[int] | None = None


# --- OUTPUT: Schemas de saída (backend → frontend) ---
class OrdemMissaoOut(OrdemMissaoCore):
    """Resposta completa de uma OM"""

    id: int
    numero: str
    campos_especiais: list[CampoEspecial] = []
    etapas: list[EtapaOut] = []
    tripulacao: list[TripulacaoOrdemOut] = []
    etiquetas: list[EtiquetaSchema] = []

    created_by: int
    created_at: Annotated[datetime, Body()]
    updated_at: Annotated[datetime | None, Body()] = None
    deleted_at: Annotated[datetime | None, Body()] = None

    model_config = ConfigDict(from_attributes=True)


class OrdemMissaoList(OrdemMissaoCore):
    """Resposta simplificada para listagem de OMs"""

    id: int
    numero: str
    esf_aer: int
    etapas: list[EtapaListItem] = []
    etiquetas: list[EtiquetaSchema] = []

    created_at: Annotated[datetime, Body()]
    updated_at: Annotated[datetime | None, Body()] = None

    model_config = ConfigDict(from_attributes=True)


# --- Sugestão de Rota ---
class RouteSuggestionOut(BaseModel):
    """Sugestão de rota baseada em missões anteriores"""

    origem: str
    dest: str
    tvoo_etp: int  # tempo de voo em minutos
    alternativa: str
    tvoo_alt: int
    qtd_comb: int

    model_config = ConfigDict(from_attributes=True)
