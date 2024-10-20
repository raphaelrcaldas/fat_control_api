from typing import Literal

from pydantic import BaseModel, Field

from fcontrol_api.schemas.funcs import FuncSchema
from fcontrol_api.schemas.users import UserTrip

uaes = Literal['11gt']


class TripSchema(BaseModel):
    user_id: int
    trig: str = Field(min_length=3, max_length=3)
    uae: uaes
    funcs: list[FuncSchema]


class TripUpdate(BaseModel):
    trig: str = Field(min_length=3, max_length=3)
    active: bool = True
    funcs: list[FuncSchema]


class TripWithFuncs(BaseModel):
    user: UserTrip
    trig: str = Field(min_length=3, max_length=3)
    uae: uaes
    funcs: list[FuncSchema]
    # model_config = ConfigDict(from_attributes=True)


class TripsListWithFuncs(BaseModel):
    data: list[TripWithFuncs]
