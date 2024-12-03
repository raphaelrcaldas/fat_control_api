from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.funcoes import FuncPublic
from fcontrol_api.schemas.tripulantes import TripWithFuncs


class QuadSchema(BaseModel):
    trip_id: int
    description: str
    type: str
    value: int = Field(ge=0)


class QuadPublic(QuadSchema):
    id: int
    # trip: TripPublic
    # model_config = ConfigDict(from_attributes=True)


class QuadList(BaseModel):
    quads: list[QuadPublic]


class QuadUpdate(BaseModel):
    value: int
    type: str
    description: str


class ResQuad(FuncPublic):
    quads: list
    trip: TripWithFuncs
