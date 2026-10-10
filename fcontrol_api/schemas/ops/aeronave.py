from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SitAeronave = Literal['DI', 'DO', 'IN', 'IS']


class ProjetoAnvOut(BaseModel):
    id_projeto: str
    modelo: str

    model_config = ConfigDict(from_attributes=True)


def _obs_vazia_vira_none(v: object) -> object:
    """Apara a `obs`; vazia ou só espaços grava NULL, não `''`."""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class AeronaveCreate(BaseModel):
    matricula: str = Field(min_length=4, max_length=4, pattern=r'^\d{4}$')
    active: bool = True
    sit: SitAeronave
    obs: str | None = None
    is_sim: bool = False
    projeto: str = Field(min_length=2, max_length=2)

    _obs_vazia = field_validator('obs', mode='before')(_obs_vazia_vira_none)


class AeronaveUpdate(BaseModel):
    # Sem `projeto`: o modelo físico de uma cauda não muda, e como
    # `tenant_projetos` é N:M, trocar o projeto tiraria a aeronave da frota
    # de outra org que opera o projeto antigo. `extra='forbid'` faz o envio
    # de `projeto` (ou de campo desconhecido) responder 422, em vez de ser
    # ignorado em silêncio.
    active: bool | None = None
    sit: SitAeronave | None = None
    obs: str | None = None
    is_sim: bool | None = None

    model_config = ConfigDict(extra='forbid')

    _obs_vazia = field_validator('obs', mode='before')(_obs_vazia_vira_none)

    @field_validator('active', 'sit', 'is_sim', mode='before')
    @classmethod
    def nao_nulo(cls, v: object) -> object:
        """Barra `null` explícito em coluna NOT NULL (seria 500 no commit).

        O campo omitido não passa por aqui (`validate_default` é False),
        então a atualização parcial continua valendo.
        """
        if v is None:
            raise ValueError('Campo não pode ser nulo')
        return v


class AeronavePublic(BaseModel):
    matricula: str
    active: bool
    # sit fica como `str` (nao `SitAeronave`) de proposito: pode haver
    # linha legada no banco com valor fora do dominio atual, e apertar a
    # saida faria o model_validate explodir num GET por causa de dado
    # antigo. Aqui so a entrada (Create/Update) e restrita.
    sit: str
    obs: str | None
    is_sim: bool
    projeto: str
    proj: ProjetoAnvOut
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
