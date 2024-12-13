from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.funcoes import FuncPublic
from fcontrol_api.schemas.users import UserPublic

uaes = Literal['11gt']


class BaseTrip(BaseModel):
    trig: str = Field(min_length=3, max_length=3)
    active: bool = True


class TripSchema(BaseTrip):
    user_id: int
    uae: uaes
    model_config = ConfigDict(from_attributes=True)


class TripWithFuncs(BaseModel):
    id: int
    trig: str = Field(min_length=3, max_length=3)
    uae: uaes
    active: bool
    user: UserPublic
    funcs: list[FuncPublic]
    model_config = ConfigDict(from_attributes=True)
