from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from fcontrol_api.schemas.users import UserPublic


class DadosBancariosBase(BaseModel):
    banco: str
    codigo_banco: str
    agencia: str
    conta: str

    remuneracao: Optional[Decimal] = Field(default=None, ge=0)
    mes_ano: Optional[date] = None
    aux_transp: Optional[Decimal] = Field(default=None, ge=0)

    model_config = ConfigDict(from_attributes=True)


class DadosBancariosCreate(DadosBancariosBase):
    user_id: int


class DadosBancariosUpdate(DadosBancariosBase):
    banco: Optional[str] = None
    codigo_banco: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None


class DadosBancariosPublic(DadosBancariosBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_serializer('remuneracao', 'aux_transp')
    def serialize_decimal(self, v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None


class DadosBancariosWithUser(DadosBancariosPublic):
    user: UserPublic


class DadosBancariosBulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1)


class DadosBancariosBulkDeleteResponse(BaseModel):
    deleted: int
