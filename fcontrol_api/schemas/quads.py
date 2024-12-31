from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.funcoes import FuncPublic
from fcontrol_api.schemas.tripulantes import TripWithFuncs


class BaseQuad(BaseModel):
    value: Annotated[date | None, Body()]
    type: str
    description: Annotated[str | None, Body()]


class QuadSchema(BaseQuad):
    trip_id: int


class QuadPublic(BaseQuad):
    id: int
    model_config = ConfigDict(from_attributes=True)


class QuadUpdate(BaseQuad): ...


class QuadList(BaseModel):
    quads: list[QuadPublic]


class ResQuad(FuncPublic):
    quads: list
    trip: TripWithFuncs
