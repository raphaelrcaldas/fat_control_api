from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizacaoBase(BaseModel):
    sigla: str = Field(max_length=20)
    nome: str = Field(max_length=150)
    sigla_2: str | None = Field(default=None, max_length=20)
    sigla_3: str | None = Field(default=None, max_length=20)
    alias: str | None = Field(default=None, max_length=100)


class OrganizacaoCreate(OrganizacaoBase):
    pass


class OrganizacaoUpdate(BaseModel):
    """Atualizacao parcial - todos os campos opcionais."""

    sigla: str | None = Field(default=None, max_length=20)
    sigla_2: str | None = Field(default=None, max_length=20)
    sigla_3: str | None = Field(default=None, max_length=20)
    nome: str | None = Field(default=None, max_length=150)
    alias: str | None = Field(default=None, max_length=100)


class OrganizacaoOut(OrganizacaoBase):
    model_config = ConfigDict(from_attributes=True)

    brasao_path: str | None = None
    created_at: datetime
