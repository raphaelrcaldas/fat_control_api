from typing import Literal

from pydantic import BaseModel, Field

from fcontrol_api.schemas.funcoes import FuncPublic
from fcontrol_api.schemas.users import UserPublic

uaes = Literal['11gt']


class BaseTrip(BaseModel):
    trig: str = Field(min_length=3, max_length=3)
    active: bool = True


class TripSchema(BaseTrip):
    user_id: int
    uae: uaes


class TripUpdate(BaseTrip):
    ...


class TripWithFuncs(BaseModel):
    id: int
    user: UserPublic
    trig: str = Field(min_length=3, max_length=3)
    uae: uaes
    active: bool
    funcs: list[FuncPublic]
