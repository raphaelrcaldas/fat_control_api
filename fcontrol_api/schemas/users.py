from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict, EmailStr, Field, create_model

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
    unidade: str
    ant_rel: int | None = Field(gt=0)
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


# cria UserUpdate dinamicamente a partir dos campos de UserSchema
_base_fields: dict = {}
for name, info in UserSchema.model_fields.items():
    _base_fields[name] = (info.annotation, None)

# opcional: incluir campos adicionais presentes em UserFull (ex: posto)
# if 'UserFull' in globals() and 'posto' in UserFull.model_fields:
#     posto_info = UserFull.model_fields['posto']
#     _base_fields['posto'] = (posto_info.annotation, None)

UserUpdate = create_model(
    'UserUpdate',
    __base__=BaseModel,
    **_base_fields,
)
UserUpdate.model_config = ConfigDict(from_attributes=True)
UserUpdate.__doc__ = 'Schema para atualização parcial do usuário.'
