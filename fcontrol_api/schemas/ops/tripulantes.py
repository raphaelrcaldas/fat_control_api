from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.funcoes import BaseFunc
from fcontrol_api.schemas.users import UserPublic


class BaseTrip(BaseFunc):
    trig: str = Field(min_length=3, max_length=3)
    active: bool = True

    @field_validator('trig')
    @classmethod
    def validate_trig(cls, v: str) -> str:
        """Valida que trig contém apenas letras."""
        if not v.isalpha():
            raise ValueError('Trigrama deve conter apenas letras')
        return v.lower()

    @model_validator(mode='after')
    def validate_data_op(self) -> 'BaseTrip':
        """Tripulante operacional (oper != 'al') exige data_op."""
        if self.oper != 'al' and self.data_op is None:
            raise ValueError('Data operacional é obrigatória para não-alunos')
        return self


class TripCreate(BaseTrip):
    """Entrada de criação. A UAE vem da org ativa do token, não do body."""

    user_id: int


class TripSchema(BaseTrip):
    user_id: int
    model_config = ConfigDict(from_attributes=True)


class TripBasicInfo(BaseModel):
    id: int
    trig: str = Field(min_length=3, max_length=3)
    active: bool
    user: UserPublic
    model_config = ConfigDict(from_attributes=True)


class TripWithFunc(TripBasicInfo, BaseFunc):
    """Tripulante com os campos da função única (1:1)."""


class TripSearchResult(BaseModel):
    id: int
    trig: str
    p_g: PostoGradEnum
    nome_guerra: str
    oper: str
    posto_ant: int
    ult_promo: date | None
    ant_rel: int | None
    id_fab: str | None
    model_config = ConfigDict(from_attributes=True)
