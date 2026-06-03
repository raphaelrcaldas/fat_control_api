from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.funcoes import BaseFunc, FuncPublic
from fcontrol_api.schemas.funcoes import funcs as FuncLiteral
from fcontrol_api.schemas.ops.tripulantes import TripWithFuncs
from fcontrol_api.schemas.users import UserPublic


class BaseQuad(BaseModel):
    value: Annotated[date | None, Body()]
    type_id: int
    description: Annotated[str | None, Body()]


class QuadSchema(BaseQuad):
    trip_id: int


class QuadPublic(BaseQuad):
    id: int
    model_config = ConfigDict(from_attributes=True)


class QuadUpdate(BaseModel):
    id: int
    trip_id: int
    value: Annotated[date | None, Body()]
    description: Annotated[str | None, Body()]


class QuadBatchDelete(BaseModel):
    ids: list[int]


class QuadList(BaseModel):
    quads: list[QuadPublic]


class ResQuad(FuncPublic):
    quads: list
    trip: TripWithFuncs


class QuadsTypeSchema(BaseModel):
    id: int
    short: str
    long: str
    funcs_list: list[str]


class QuadsGroupSchema(BaseModel):
    id: int
    short: str
    long: str
    types: list[QuadsTypeSchema]


# ---------------------------------------------------------------------------
# Gerenciamento da estrutura de quadrinhos (Group -> Type -> Func)
# ---------------------------------------------------------------------------


class QuadsGroupCreate(BaseModel):
    short: str = Field(min_length=1, max_length=50)
    long: str = Field(min_length=1, max_length=150)


class QuadsGroupUpdate(BaseModel):
    short: str | None = Field(default=None, min_length=1, max_length=50)
    long: str | None = Field(default=None, min_length=1, max_length=150)


class QuadsGroupOut(BaseModel):
    id: int
    short: str
    long: str
    uae: str
    model_config = ConfigDict(from_attributes=True)


class QuadsTypeCreate(BaseModel):
    short: str = Field(min_length=1, max_length=50)
    long: str = Field(min_length=1, max_length=150)


class QuadsTypeUpdate(BaseModel):
    short: str | None = Field(default=None, min_length=1, max_length=50)
    long: str | None = Field(default=None, min_length=1, max_length=150)


class QuadsTypeOut(BaseModel):
    id: int
    group_id: int
    short: str
    long: str
    funcs_list: list[str]
    model_config = ConfigDict(from_attributes=True)


class QuadsFuncsSet(BaseModel):
    """Define o conjunto de funções que concorrem a um tipo.

    Substitui a associação inteira (operação declarativa). Qualquer função
    do enum é aceita — funções esporádicas (ml/md) simplesmente não são
    cadastradas na prática.
    """

    funcs: list[FuncLiteral] = Field(default_factory=list)


class TripQuadInfo(BaseModel):
    """Dados do tripulante no contexto de quadrinhos."""

    id: int
    trig: str
    user: UserPublic
    func: BaseFunc | None = None

    model_config = ConfigDict(from_attributes=True)


class TripQuadEntry(BaseModel):
    trip: TripQuadInfo
    quads: list[QuadPublic]
    quads_len: int


class QuadsOrfaoEntry(BaseModel):
    trip: TripQuadInfo
    quads_count: int


class QuadsOrfaosDelete(BaseModel):
    trip_ids: list[int] = Field(min_length=1)


class QuadsOrfaosDeleteResponse(BaseModel):
    deleted: int
    trips: int
