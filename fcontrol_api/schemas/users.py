from datetime import datetime
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, EmailStr


class UserSchema(BaseModel):
    p_g: str
    nome_guerra: str
    nome_completo: str
    esp: str
    id_fab: int | None
    saram: int
    cpf: str
    ult_promo: Annotated[datetime | None, Body()]
    nasc: Annotated[datetime | None, Body()]
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
