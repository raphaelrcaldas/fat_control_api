from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserSchema(BaseModel):
    pg: str
    nome_guerra: str
    nome_completo: str | None
    ult_promo: datetime | None
    id_fab: int | None
    saram: int | None
    cpf: str | None
    nasc: datetime | None
    celular: str | None
    email_pess: EmailStr | None
    email_fab: EmailStr | None
    unidade: str


class UserPublic(BaseModel):
    pg: str
    nome_guerra: str
    unidade: str
    saram: int


class ListUsers(BaseModel):
    data: list[UserPublic]


class MessageCreateUser(BaseModel):
    detail: str
    data: UserPublic
