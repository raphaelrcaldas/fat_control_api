from pydantic import BaseModel

from .tripulantes import TripSchema
from .users import UserPublic


class Message(BaseModel):
    detail: str


class UserMessage(Message):
    data: UserPublic


class TripMessage(Message):
    data: TripSchema
