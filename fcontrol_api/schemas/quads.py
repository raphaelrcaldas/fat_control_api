from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.funcs import FuncPublic
from fcontrol_api.schemas.tripulantes import TripWithFuncs


class QuadType(str, Enum):
    # SOBREAVISO
    sobr_pto = 's_pto'
    sobr_vmo = 's_vmo'
    sobr_rxo = 's_rxo'

    # LOCAL
    local = 'local'

    # NACIONAL
    nacional = 'nacional'
    sar = 'sar'

    # DESLOCAMENTO
    desloc = 'desloc'


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
