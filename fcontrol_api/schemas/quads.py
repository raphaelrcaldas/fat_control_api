from enum import Enum

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.tripulantes import TripPublic


class QuadType(str, Enum):
    nacional = 'nacional'
    local = 'local'
    desloc = 'desloc'
    sobr = 'sobr'
    sar = 'sar'


class QuadSchema(BaseModel):
    trip_id: int
    description: str
    type: QuadType
    value: int


class QuadPublic(QuadSchema):
    id: int
    trip: TripPublic
    model_config = ConfigDict(from_attributes=True)


class QuadList(BaseModel):
    quads: list[QuadPublic]


class QuadUpdate(BaseModel):
    value: int
    type: QuadType
    description: str
