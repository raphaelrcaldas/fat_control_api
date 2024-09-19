from enum import Enum

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.users import UserPublic


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
    id: int
    trig: str
    func: FuncList
    oper: OperList
    active: bool = True


class TripPublic(TripSchema):
    user: UserPublic
    model_config = ConfigDict(from_attributes=True)


class TripList(BaseModel):
    trips: list[TripPublic]
