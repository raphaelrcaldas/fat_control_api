from enum import Enum

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.funcs import FuncPublic
from fcontrol_api.schemas.users import UserTrip


class FuncList(str, Enum):
    mc = 'mc'
    lm = 'lm'
    tf = 'tf'
    os = 'os'
    oe = 'oe'


class OperList(str, Enum):
    alno = 'al'  # ALUNO
    basc = 'ba'  # BASICO
    oper = 'op'  # OPERACIONAL
    inst = 'in'  # INSTRUTOR


class TripSchema(BaseModel):
    user_id: int
    trig: str
    active: bool = True
    uae: str


class TripUpdate(BaseModel):
    trig: str
    active: bool = True


class TripWithFuncs(TripSchema):
    user: UserTrip
    funcs: list[FuncPublic]
    # model_config = ConfigDict(from_attributes=True)


class TripsListWithFuncs(BaseModel):
    data: list[TripWithFuncs]
