from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SitAeronave = Literal['DI', 'DO', 'IN', 'IS']


class ProjetoAnvOut(BaseModel):
    id_projeto: str
    modelo: str

    model_config = ConfigDict(from_attributes=True)


class AeronaveCreate(BaseModel):
    matricula: str = Field(min_length=4, max_length=4, pattern=r'^\d{4}$')
    active: bool = True
    sit: SitAeronave
    obs: str | None = None
    is_sim: bool = False
    projeto: str = Field(min_length=2, max_length=2)


class AeronaveUpdate(BaseModel):
    active: bool | None = None
    sit: SitAeronave | None = None
    obs: str | None = None
    is_sim: bool | None = None
    projeto: str | None = Field(None, min_length=2, max_length=2)


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
