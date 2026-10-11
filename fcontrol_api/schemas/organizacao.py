from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Sigla = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)
]
Nome = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]


class OrganizacaoBase(BaseModel):
    sigla: str = Field(max_length=20)
    nome: str = Field(max_length=150)
    sigla_2: str | None = Field(default=None, max_length=20)
    sigla_3: str | None = Field(default=None, max_length=20)
    alias: str | None = Field(default=None, max_length=100)


class OrganizacaoCreate(OrganizacaoBase):
    # A sigla é a PK: vazia (ou só espaços) não identifica nada.
    sigla: Sigla
    nome: Nome


class OrganizacaoUpdate(BaseModel):
    """Atualizacao parcial - todos os campos opcionais.

    `sigla` e `nome` podem ser omitidos, mas não enviados como `null`: as
    colunas são NOT NULL e o IntegrityError virava o 409 de sigla duplicada.
    """

    sigla: Sigla | None = None
    sigla_2: str | None = Field(default=None, max_length=20)
    sigla_3: str | None = Field(default=None, max_length=20)
    nome: Nome | None = None
    alias: str | None = Field(default=None, max_length=100)

    @field_validator('sigla', 'nome')
    @classmethod
    def rejeitar_nulo(cls, v: str | None) -> str:
        if v is None:
            raise ValueError('não pode ser nulo')
        return v


class OrganizacaoOut(OrganizacaoBase):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
