from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class CidadeSchema(BaseModel):
    codigo: int
    nome: str
    uf: str
    model_config = ConfigDict(from_attributes=True)


class GrupoCidadePublic(BaseModel):
    id: int
    grupo: int
    cidade_id: int
    cidade: CidadeSchema | None = None
    model_config = ConfigDict(from_attributes=True)


class GrupoPgPublic(BaseModel):
    id: int
    grupo: int
    pg_short: str
    pg_mid: str | None = None
    pg_long: str | None = None
    circulo: str | None = None
    model_config = ConfigDict(from_attributes=True)


class DiariaValorPublic(BaseModel):
    id: int
    grupo_pg: int
    grupo_cid: int
    valor: Decimal
    data_inicio: date
    data_fim: date | None
    status: str | None = None  # vigente, proximo, anterior
    model_config = ConfigDict(from_attributes=True)

    @field_serializer('valor')
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)


class DiariaValorUpdate(BaseModel):
    valor: Decimal | None = Field(None, gt=0)
    data_inicio: date | None = None
    data_fim: date | None = None


class DiariaValorCreate(BaseModel):
    grupo_pg: int
    grupo_cid: int
    valor: Decimal = Field(..., gt=0)
    data_inicio: date
    data_fim: date | None = None
