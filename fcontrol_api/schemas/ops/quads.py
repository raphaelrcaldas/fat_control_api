from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.funcoes import BaseFunc, FuncPublic
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
