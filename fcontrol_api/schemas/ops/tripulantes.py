from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.funcoes import FuncPublic
from fcontrol_api.schemas.users import UserPublic


class BaseTrip(BaseModel):
    trig: str = Field(min_length=3, max_length=3)
    active: bool = True

    @field_validator('trig')
    @classmethod
    def validate_trig(cls, v: str) -> str:
        """Valida que trig contém apenas letras."""
        if not v.isalpha():
            raise ValueError('Trigrama deve conter apenas letras')
        return v.lower()


class TripCreate(BaseTrip):
    """Entrada de criação. A UAE vem da org ativa do token, não do body."""

    user_id: int


class TripSchema(BaseTrip):
    user_id: int
    uae: str
    model_config = ConfigDict(from_attributes=True)


class TripBasicInfo(BaseModel):
    id: int
    trig: str = Field(min_length=3, max_length=3)
    uae: str
    active: bool
    user: UserPublic
    model_config = ConfigDict(from_attributes=True)


class TripWithFuncs(TripBasicInfo):
    funcs: list[FuncPublic]
    model_config = ConfigDict(from_attributes=True)


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
