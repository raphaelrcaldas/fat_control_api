from datetime import date
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.pagination import PaginatedResponse
from fcontrol_api.schemas.posto_grad import PostoGradSchema
from fcontrol_api.utils.validators import (
    validar_cpf,
    validar_saram,
    validar_zimbra,
)


class UserSchema(BaseModel):
    p_g: PostoGradEnum
    esp: str
    nome_guerra: str
    nome_completo: str
    id_fab: str | None = Field(default=None, min_length=6, max_length=6)
    saram: str = Field(min_length=7, max_length=7)
    cpf: str
    ult_promo: Annotated[date | None, Body()]
    nasc: Annotated[date | None, Body()]
    email_pess: EmailStr | None
    email_fab: EmailStr | None
    active: bool
    unidade: str
    ant_rel: int | None = Field(gt=0)

    model_config = ConfigDict(from_attributes=True)

    @field_validator('id_fab')
    @classmethod
    def validate_id_fab(cls, v: str | None) -> str | None:
        """
        Valida que id_fab contém apenas dígitos.
        """
        if v is not None and not v.isdigit():
            raise ValueError('ID FAB deve conter apenas dígitos')
        return v

    @field_validator('saram')
    @classmethod
    def validate_saram(cls, v: str) -> str:
        """
        Valida o dígito verificador do SARAM.
        Usa algoritmo módulo 11 com pesos de 2 a 7.
        """
        if not v.isdigit():
            raise ValueError('SARAM deve conter apenas dígitos')
        if not validar_saram(v):
            raise ValueError('SARAM inválido')
        return v

    @field_validator('cpf')
    @classmethod
    def validate_cpf(cls, v: str) -> str:
        """
        Valida o CPF brasileiro.
        Permite string vazia (CPF opcional).
        """
        if v and not validar_cpf(v):
            raise ValueError('CPF inválido')
        return v

    @field_validator('email_fab')
    @classmethod
    def validate_email_fab(cls, v: str) -> str:
        """
        Valida que o email FAB (Zimbra) termina com @fab.mil.br.
        """
        if v and not validar_zimbra(v):
            raise ValueError('Email FAB deve terminar com @fab.mil.br')
        return v


class UserUpdate(BaseModel):
    """Schema para atualização parcial do usuário.

    Todos os campos são opcionais. Apenas os campos fornecidos
    serão atualizados no banco de dados.
    """

    p_g: PostoGradEnum | None = None
    esp: str | None = None
    nome_guerra: str | None = None
    nome_completo: str | None = None
    id_fab: str | None = Field(default=None, min_length=6, max_length=6)
    saram: str | None = Field(default=None, min_length=7, max_length=7)
    cpf: str | None = None
    ult_promo: date | None = None
    nasc: date | None = None
    email_pess: EmailStr | None = None
    email_fab: EmailStr | None = None
    active: bool | None = None
    unidade: str | None = None
    ant_rel: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(from_attributes=True)

    @field_validator('id_fab')
    @classmethod
    def validate_id_fab(cls, v: str | None) -> str | None:
        """
        Valida que id_fab contém apenas dígitos.
        """
        if v is not None and not v.isdigit():
            raise ValueError('ID FAB deve conter apenas dígitos')
        return v

    @field_validator('saram')
    @classmethod
    def validate_saram(cls, v: str | None) -> str | None:
        """
        Valida o dígito verificador do SARAM.
        Usa algoritmo módulo 11 com pesos de 2 a 7.
        """
        if v is not None:
            if not v.isdigit():
                raise ValueError('SARAM deve conter apenas dígitos')
            if not validar_saram(v):
                raise ValueError('SARAM inválido')
        return v

    @field_validator('cpf')
    @classmethod
    def validate_cpf(cls, v: str | None) -> str | None:
        """
        Valida o CPF brasileiro.
        Permite None ou string vazia (CPF opcional).
        """
        if v and not validar_cpf(v):
            raise ValueError('CPF inválido')
        return v

    @field_validator('email_fab')
    @classmethod
    def validate_email_fab(cls, v: str | None) -> str | None:
        """
        Valida que o email FAB (Zimbra) termina com @fab.mil.br.
        Permite None (campo opcional em update), mas rejeita string vazia.
        """
        if v is not None and not validar_zimbra(v):
            raise ValueError('Email FAB deve terminar com @fab.mil.br')
        return v


class UserFull(UserSchema):
    posto: PostoGradSchema


class UserPublic(BaseModel):
    id: int
    p_g: PostoGradEnum
    posto: PostoGradSchema
    esp: str
    id_fab: str | None
    nome_guerra: str
    saram: str
    nome_completo: str
    active: bool
    unidade: str
    ult_promo: Annotated[date | None, Body()]
    ant_rel: int | None = Field(gt=0)
    model_config = ConfigDict(from_attributes=True)


class PwdSchema(BaseModel):
    new_pwd: str = Field(min_length=8, max_length=128)

    @field_validator('new_pwd')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Valida a força da senha.
        Requisitos:
        - Mínimo 8 caracteres
        - Pelo menos 1 letra maiúscula
        - Pelo menos 1 letra minúscula
        - Pelo menos 1 dígito
        - Pelo menos 1 caractere especial
        """
        import re  # noqa: PLC0415

        errors = []

        if not re.search(r'[A-Z]', v):
            errors.append('pelo menos 1 letra maiúscula')

        if not re.search(r'[a-z]', v):
            errors.append('pelo menos 1 letra minúscula')

        if not re.search(r'\d', v):
            errors.append('pelo menos 1 dígito')

        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/`~]', v):
            errors.append('pelo menos 1 caractere especial (!@#$%^&*...)')

        if errors:
            raise ValueError(f'Senha deve conter: {", ".join(errors)}')

        return v


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
