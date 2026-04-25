from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

from fcontrol_api.schemas.logs import UserSummary


class OrcamentoAnualBase(BaseModel):
    ano_ref: int = Field(ge=2026, le=2100)
    total: Decimal = Field(ge=0)
    abertura: Decimal = Field(ge=0)
    fechamento: Decimal = Field(ge=0)

    @model_validator(mode='after')
    def check_soma(self):
        if self.abertura + self.fechamento != self.total:
            raise ValueError(
                'A soma das cotas (abertura + fechamento) deve ser '
                'igual ao orçamento total.'
            )
        return self


class OrcamentoAnualCreate(OrcamentoAnualBase):
    pass


class OrcamentoAnualUpdate(OrcamentoAnualBase):
    pass


class OrcamentoAnualOut(OrcamentoAnualBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('total', 'abertura', 'fechamento')
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)


class OrcamentoLogOut(BaseModel):
    id: int
    user: UserSummary
    action: str
    before: dict | None
    after: dict | None
    timestamp: datetime
