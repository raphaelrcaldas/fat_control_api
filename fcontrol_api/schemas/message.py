from pydantic import BaseModel

from .funcoes import FuncPublic
from .tripulantes import TripSchema
from .users import UserPublic


class Message(BaseModel):
    detail: str


class UserMessage(Message):
    data: UserPublic


class TripMessage(Message):
    data: TripSchema


class FuncMessage(Message):
    data: FuncPublic
