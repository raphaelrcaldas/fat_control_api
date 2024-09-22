from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, EmailStr, Field


class UserSchema(BaseModel):
    p_g: str
    nome_guerra: str
    nome_completo: str
    esp: str
    id_fab: int | None = Field(gt=100000)
    saram: int = Field(gt=1000000, lt=9999999)
    cpf: str
    ult_promo: Annotated[date | None, Body()]
    nasc: Annotated[date | None, Body()]
    email_pess: EmailStr | str
    email_fab: EmailStr | str
    unidade: str


class UserPublic(BaseModel):
    id: int
    p_g: str
    esp: str
    nome_guerra: str
    nome_completo: str
    unidade: str


class ListUsers(BaseModel):
    data: list[UserPublic]


class UserTrip(BaseModel):
    p_g: str
    esp: str
    nome_guerra: str
