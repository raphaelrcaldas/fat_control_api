from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.users import UserPublic


class DadosBancariosBase(BaseModel):
    banco: str
    codigo_banco: str
    agencia: str
    conta: str

    model_config = ConfigDict(from_attributes=True)


class DadosBancariosCreate(DadosBancariosBase):
    user_id: int


class DadosBancariosUpdate(DadosBancariosBase):
    banco: Optional[str] = None
    codigo_banco: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None


class DadosBancariosPublic(DadosBancariosBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class DadosBancariosWithUser(DadosBancariosPublic):
    user: UserPublic
