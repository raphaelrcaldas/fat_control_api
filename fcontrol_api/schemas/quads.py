from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.funcoes import FuncPublic
from fcontrol_api.schemas.tripulantes import TripWithFuncs


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


class QuadList(BaseModel):
    quads: list[QuadPublic]


class ResQuad(FuncPublic):
    quads: list
    trip: TripWithFuncs


class QuadsFunc(BaseModel):
    id: int
    func: str


class QuadsTypeSchema(BaseModel):
    id: int
    short: str
    long: str
    funcs: list[QuadsFunc]


class QuadsGroupSchema(BaseModel):
    id: int
    short: str
    long: str
    types: list[QuadsTypeSchema]
