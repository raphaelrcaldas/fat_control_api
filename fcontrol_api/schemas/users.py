from datetime import date
from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, ConfigDict, EmailStr, Field

p_gs = Literal['so', '1s', '2s', '3s']


class UserSchema(BaseModel):
    p_g: p_gs
    esp: str
    nome_guerra: str
    nome_completo: str
    id_fab: int | None = Field(gt=100000)
    saram: int = Field(gt=1000000, lt=9999999)
    cpf: str
    ult_promo: Annotated[date | None, Body()]
    nasc: Annotated[date | None, Body()]
    email_pess: EmailStr | str
    email_fab: EmailStr | str
    unidade: str
    model_config = ConfigDict(from_attributes=True)


class UserPublic(BaseModel):
    id: int
    p_g: p_gs
    esp: str
    nome_guerra: str
    nome_completo: str
    unidade: str
    model_config = ConfigDict(from_attributes=True)


class UserTrip(BaseModel):
    id: int
    p_g: p_gs
    esp: str
    nome_guerra: str
    nome_completo: str
    unidade: str
