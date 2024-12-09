from typing import Literal

from pydantic import BaseModel, Field

from fcontrol_api.schemas.funcoes import FuncPublic, FuncSchema
from fcontrol_api.schemas.users import UserTrip

uaes = Literal['11gt']


class TripSchema(BaseModel):
    user_id: int
    trig: str = Field(min_length=3, max_length=3)
    uae: uaes
    active: bool = True
    # funcs: list[FuncSchema]


class TripUpdate(BaseModel):
    trig: str = Field(min_length=3, max_length=3)
    active: bool
    # funcs: list[FuncSchema]


class TripWithFuncs(BaseModel):
    id: int
    user: UserTrip
    trig: str = Field(min_length=3, max_length=3)
    uae: uaes
    active: bool
    funcs: list[FuncPublic]
    # model_config = ConfigDict(from_attributes=True)
