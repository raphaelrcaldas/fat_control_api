from datetime import date, datetime
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.users import UserPublic


class BaseIndisp(BaseModel):
    date_start: Annotated[date, Body()]
    date_end: Annotated[date, Body()]
    mtv: str
    obs: str | None


class IndispSchema(BaseIndisp):
    user_id: int


class IndispOut(IndispSchema):
    id: int
    created_at: Annotated[datetime, Body()]
    user_created: UserPublic
    model_config = ConfigDict(from_attributes=True)
