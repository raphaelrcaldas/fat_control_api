from datetime import date

from pydantic import BaseModel, ConfigDict


class SeboVoo(BaseModel):
    """Dados de voo agregados."""

    h_ano: int
    dsv: int | None
    data_ult_voo: date | None


class SeboCartoes(BaseModel):
    """Cartoes de validade (Aeromedica, SegVoo, Inteligencia)."""

    # Aeromedica
    cemal: date | None = None
    tovn: date | None = None
    imae: date | None = None

    # Seguranca de Voo
    crm: date | None = None

    # Inteligencia
    val_pass: date | None = None
    val_visa: date | None = None


class SeboTripOut(BaseModel):
    """Dados agregados do Pau de Sebo por tripulante."""

    trip_id: int
    p_g: str
    nome_guerra: str
    trig: str
    func: str
    oper: str
    voo: SeboVoo
    cartoes: SeboCartoes

    model_config = ConfigDict(from_attributes=True)
