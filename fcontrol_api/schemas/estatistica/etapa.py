from datetime import date, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EtapaBase(BaseModel):
    """Campos compartilhados entre entrada e saida."""

    data: date
    origem: str = Field(min_length=4, max_length=4)
    destino: str = Field(min_length=4, max_length=4)
    dep: time
    arr: time
    tvoo: int = Field(ge=5)
    anv: str = Field(max_length=4)
    pousos: int = Field(ge=0, le=32767)
    tow: int | None = Field(None, gt=0)
    pax: int | None = Field(None, ge=0, le=32767)
    carga: int | None = Field(None, ge=0, le=32767)
    comb: int | None = Field(None, gt=0, le=32767)
    lub: float | None = Field(None, ge=0, le=9999.9)
    nivel: str | None = Field(None, pattern=r'^\d{3}$')
    sagem: bool
    parte1: bool
    obs: str | None

    @model_validator(mode='after')
    def validate_tvoo(self) -> Self:
        """Valida consistencia de tvoo com dep/arr."""
        dep_min = self.dep.hour * 60 + self.dep.minute
        arr_min = self.arr.hour * 60 + self.arr.minute
        if arr_min < dep_min:
            arr_min += 1440  # +24h
        expected = arr_min - dep_min
        if self.tvoo != expected:
            msg = (
                f'tvoo ({self.tvoo}) nao confere com dep/arr ({expected} min)'
            )
            raise ValueError(msg)
        return self


class EtapaOut(BaseModel):
    """Schema de saida para listagem de etapas."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    data: date
    origem: str
    destino: str
    dep: time
    arr: time
    tvoo: int
    anv: str
    tow: int | None
    pax: int | None
    carga: int | None
    comb: int | None
    lub: float | None
    nivel: str | None
    sagem: bool
    parte1: bool
    obs: str | None
    tripulantes: list['TripEtapaOut'] = []
    oi_etapas: list['OIEtapaOut'] = []


class EtapaFlatOut(EtapaOut):
    """Schema de saida para listagem flat."""

    missao_id: int
    missao_titulo: str | None = None


class MissaoComEtapasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
    is_simulador: bool = False
    etapas: list[EtapaOut]


class TripEtapaOut(BaseModel):
    """Tripulante vinculado a uma etapa."""

    trip_id: int
    trig: str
    nome_guerra: str
    p_g: str
    func: str
    func_bordo: str


class OIEtapaOut(BaseModel):
    """Ordem de Instrucao vinculada a uma etapa."""

    esf_aer_id: int
    tipo_missao_id: int
    esf_aer: str
    tipo_missao_cod: str
    reg: str
    tvoo: int


class EtapaDetailOut(EtapaOut):
    """Detalhe completo de uma etapa."""

    pousos: int


class TripEtapaIn(BaseModel):
    """Tripulante a vincular em uma etapa."""

    trip_id: int
    func: str
    func_bordo: str


class OIEtapaIn(BaseModel):
    """Ordem de Instrucao a vincular em uma etapa."""

    esf_aer_id: int
    tipo_missao_id: int
    reg: str = Field(pattern=r'^[dnv]$')
    tvoo: int = Field(gt=0, le=32767)


class EtapaCreate(EtapaBase):
    """Schema de criacao de etapa com tripulantes."""

    missao_id: int
    tripulantes: list[TripEtapaIn] = []
    oi_etapas: list[OIEtapaIn] = []


class EtapaUpdate(BaseModel):
    """Schema de atualizacao (campos opcionais)."""

    data: date | None = None
    origem: str | None = Field(None, min_length=4, max_length=4)
    destino: str | None = Field(None, min_length=4, max_length=4)
    dep: time | None = None
    arr: time | None = None
    tvoo: int | None = Field(None, ge=5)
    anv: str | None = Field(None, max_length=4)
    pousos: int | None = Field(None, ge=0, le=32767)
    tow: int | None = Field(None, gt=0)
    pax: int | None = Field(None, ge=0, le=32767)
    carga: int | None = Field(None, ge=0, le=32767)
    comb: int | None = Field(None, gt=0, le=32767)
    lub: float | None = Field(None, ge=0, le=9999.9)
    nivel: str | None = Field(None, pattern=r'^\d{3}$')
    sagem: bool | None = None
    parte1: bool | None = None
    obs: str | None = None
    tripulantes: list[TripEtapaIn] | None = None
    oi_etapas: list[OIEtapaIn] | None = None


class EtapaPublic(BaseModel):
    """Schema de resposta apos criar/atualizar."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class EtapaExportRequest(BaseModel):
    """Requisicao de exportacao de etapas para Excel."""

    ids: list[int] = Field(min_length=1)
    pousos: bool = False
    nivel: bool = False
    tow: bool = False
    pax: bool = False
    carga: bool = False
    comb: bool = False
    lub: bool = False
    esforco_aereo: bool = False
    tripulantes: bool = False


class MissaoCreate(BaseModel):
    titulo: str | None = None
    obs: str | None = None
    is_simulador: bool = False


class MissaoUpdate(BaseModel):
    titulo: str | None = None
    obs: str | None = None


class MissaoPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
    is_simulador: bool = False
