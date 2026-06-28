from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from fcontrol_api.schemas.posto_grad import PostoGradSchema


class SoldoCreate(BaseModel):
    pg: str = Field(..., min_length=1, max_length=10)
    data_inicio: date
    data_fim: date | None = None
    valor: Decimal = Field(..., gt=0)


class SoldoUpdate(BaseModel):
    pg: str | None = Field(None, min_length=1, max_length=10)
    data_inicio: date | None = None
    data_fim: date | None = None
    valor: Decimal | None = Field(None, gt=0)


class SoldoPublic(BaseModel):
    id: int
    pg: str
    data_inicio: date
    data_fim: date | None
    valor: Decimal
    posto_grad: PostoGradSchema | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('valor')
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)


class SoldoStats(BaseModel):
    total: int
    min_valor: Decimal | None
    max_valor: Decimal | None

    @field_serializer('min_valor', 'max_valor')
    def serialize_decimal(self, v: Decimal | None) -> float | None:
        return float(v) if v is not None else None
