from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from fcontrol_api.schemas.pagination import PaginatedResponse
from fcontrol_api.schemas.posto_grad import PostoGradSchema


class UserSchema(BaseModel):
    p_g: str
    esp: str
    nome_guerra: str
    nome_completo: str
    id_fab: int | None = Field(ge=100000)
    saram: int = Field(ge=1000000, le=9999999)
    cpf: str
    ult_promo: Annotated[date | None, Body()]
    nasc: Annotated[date | None, Body()]
    email_pess: EmailStr | str
    email_fab: EmailStr | str
    active: bool
    unidade: str
    ant_rel: int | None = Field(gt=0)

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """Schema para atualização parcial do usuário.

    Todos os campos são opcionais. Apenas os campos fornecidos
    serão atualizados no banco de dados.
    """

    p_g: str | None = None
    esp: str | None = None
    nome_guerra: str | None = None
    nome_completo: str | None = None
    id_fab: int | None = Field(default=None, ge=100000)
    saram: int | None = Field(default=None, ge=1000000, le=9999999)
    cpf: str | None = None
    ult_promo: date | None = None
    nasc: date | None = None
    email_pess: EmailStr | str | None = None
    email_fab: EmailStr | str | None = None
    active: bool | None = None
    unidade: str | None = None
    ant_rel: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(from_attributes=True)


class UserFull(UserSchema):
    posto: PostoGradSchema


class UserPublic(BaseModel):
    id: int
    p_g: str
    posto: PostoGradSchema
    esp: str
    nome_guerra: str
    saram: int
    nome_completo: str
    active: bool
    unidade: str
    ult_promo: Annotated[date | None, Body()]
    ant_rel: int | None = Field(gt=0)
    model_config = ConfigDict(from_attributes=True)


class PwdSchema(BaseModel):
    new_pwd: str


class Permission(BaseModel):
    name: str
    resource: str


class UserProfile(BaseModel):
    id: int
    posto: str
    nome_guerra: str
    role: str | None
    permissions: list[Permission]

    class Config:
        from_attributes = True


class UserPublicPaginated(PaginatedResponse[UserPublic]):
    """Resposta paginada de usuários públicos."""

    pass
