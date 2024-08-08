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
    user_id: int
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
    user_id: int
    type: QuadType
    value: int


class QuadPublic(QuadSchema):
    id: int


class QuadList(BaseModel):
    quads: list[QuadPublic]


class QuadUpdate(BaseModel):
    user_id: int
    value: int
    type: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
