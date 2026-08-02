from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.funcoes import BaseFunc, funcs, opers
from fcontrol_api.schemas.users import UserPublic


def normaliza_trig(v: str) -> str:
    """Valida letras e normaliza o trigrama em MAIÚSCULAS.

    A normalizacao aqui e a unica garantia de forma canonica no banco:
    a checagem de unicidade compara por igualdade exata, entao 'abc' e
    'ABC' conviveriam como trigramas distintos se o valor chegasse cru
    ate a query.
    """
    if not v.isalpha():
        raise ValueError('Trigrama deve conter apenas letras')
    return v.upper()


# Tipo unico do trigrama: criacao e patch parcial compartilham a mesma
# regra, entao ela nao pode morar duplicada em dois schemas.
Trigrama = Annotated[
    str,
    Field(min_length=3, max_length=3),
    AfterValidator(normaliza_trig),
]


class BaseTrip(BaseFunc):
    trig: Trigrama
    active: bool = True

    @model_validator(mode='after')
    def validate_data_op(self) -> 'BaseTrip':
        """Tripulante operacional (oper != 'al') exige data_op."""
        if self.oper != 'al' and self.data_op is None:
            raise ValueError('Data operacional é obrigatória para não-alunos')
        return self


class TripCreate(BaseTrip):
    """Entrada de criação. A UAE vem da org ativa do token, não do body."""

    user_id: int


class TripUpdate(BaseModel):
    """Patch parcial de tripulante — todos os campos opcionais.

    A regra "`data_op` obrigatório quando `oper != 'al'`" precisa do
    valor efetivo pós-merge (body ∪ estado persistido) para ser
    avaliada corretamente num PATCH parcial — por isso não há
    `model_validator` aqui; a checagem sobe para a rota.
    """

    trig: Trigrama | None = None
    active: bool | None = None
    func: funcs | None = None
    oper: opers | None = None
    proj: str | None = None
    data_op: Annotated[date | None, Body()] = None
    model_config = ConfigDict(from_attributes=True)


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
