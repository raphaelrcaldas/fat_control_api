from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjetoAnvOut(BaseModel):
    id_projeto: str
    modelo: str

    model_config = ConfigDict(from_attributes=True)


class AeronaveCreate(BaseModel):
    matricula: str = Field(min_length=4, max_length=4, pattern=r'^\d{4}$')
    active: bool = True
    sit: str = Field(min_length=2, max_length=2)
    obs: str | None = None
    is_sim: bool = False
    projeto: str = Field(min_length=2, max_length=2)


class AeronaveUpdate(BaseModel):
    active: bool | None = None
    sit: str | None = Field(None, min_length=2, max_length=2)
    obs: str | None = None
    is_sim: bool | None = None
    projeto: str | None = Field(None, min_length=2, max_length=2)


class AeronavePublic(BaseModel):
    matricula: str
    active: bool
    sit: str
    obs: str | None
    is_sim: bool
    projeto: str
    proj: ProjetoAnvOut
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
