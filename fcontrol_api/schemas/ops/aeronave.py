from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AeronaveCreate(BaseModel):
    matricula: str = Field(
        min_length=4, max_length=4, pattern=r'^\d{4}$'
    )
    active: bool = True
    sit: str = Field(min_length=2, max_length=2)
    obs: str | None = None
    prox_insp: date | None = None


class AeronaveUpdate(BaseModel):
    active: bool | None = None
    sit: str | None = Field(
        None, min_length=2, max_length=2
    )
    obs: str | None = None
    prox_insp: date | None = None


class AeronavePublic(BaseModel):
    matricula: str
    active: bool
    sit: str
    obs: str | None
    prox_insp: date | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
