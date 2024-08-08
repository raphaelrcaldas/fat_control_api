from pydantic import BaseModel, ConfigDict, EmailStr

from fcontrol_api.models import FuncList, OperList, QuadType


class UserSchema(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: int
    username: str
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)


class UserDB(UserSchema):
    id: int


class UserList(BaseModel):
    users: list[UserPublic]


class TripSchema(BaseModel):
    id: int
    trig: str
    func: FuncList
    oper: OperList


class TripSchemaUpdate(BaseModel):
    "Somente para não duplicar o id na req update trip"

    trig: str
    func: FuncList
    oper: OperList


class TripPublic(TripSchema):
    user: UserPublic
    model_config = ConfigDict(from_attributes=True)


class TripList(BaseModel):
    trips: list[TripPublic]


class Message(BaseModel):
    message: str


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
