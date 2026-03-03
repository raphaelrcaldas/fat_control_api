from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field


class EtapaBase(BaseModel):
    """Campos compartilhados entre entrada e saida."""

    data: date
    origem: str = Field(min_length=4, max_length=4)
    destino: str = Field(min_length=4, max_length=4)
    dep: time
    arr: time
    tvoo: int
    anv: str
    pousos: int
    tow: int | None
    pax: int | None
    carga: int | None
    comb: int | None
    lub: float | None
    nivel: str | None = Field(None, pattern=r'^\d{3}$')
    sagem: bool
    parte1: bool
    obs: str | None


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
    esf_aer_itens: list[str] = []
    tipo_missao_cod: str | None = None
    tripulantes: dict[str, list[str]] = {}


class MissaoComEtapasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
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
    """Detalhe completo de uma etapa com tripulantes."""

    pousos: int
    tripulantes: list[TripEtapaOut] = []
    oi_etapas: list[OIEtapaOut] = []


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
    tvoo: int


class EtapaCreate(EtapaBase):
    """Schema de criacao de etapa com tripulantes e OIs."""

    missao_id: int
    tripulantes: list[TripEtapaIn] = []
    oi_etapas: list[OIEtapaIn] = []


class EtapaUpdate(BaseModel):
    """Schema de atualizacao de etapa (todos os campos opcionais)."""

    data: date | None = None
    origem: str | None = Field(None, min_length=4, max_length=4)
    destino: str | None = Field(None, min_length=4, max_length=4)
    dep: time | None = None
    arr: time | None = None
    tvoo: int | None = None
    anv: str | None = None
    pousos: int | None = None
    tow: int | None = None
    pax: int | None = None
    carga: int | None = None
    comb: int | None = None
    lub: float | None = None
    nivel: str | None = Field(None, pattern=r'^\d{3}$')
    sagem: bool | None = None
    parte1: bool | None = None
    obs: str | None = None
    tripulantes: list[TripEtapaIn] | None = None
    oi_etapas: list[OIEtapaIn] | None = None


class EtapaPublic(BaseModel):
    """Schema de resposta apos criar/atualizar etapa."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class MissaoCreate(BaseModel):
    titulo: str | None = None
    obs: str | None = None


class MissaoUpdate(BaseModel):
    titulo: str | None = None
    obs: str | None = None


class MissaoPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
