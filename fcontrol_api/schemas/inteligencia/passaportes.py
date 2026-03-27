from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


class PassaporteBase(BaseModel):
    passaporte: str | None = None
    visa: str | None = None
    validade_passaporte: date | None = None
    validade_visa: date | None = None

    model_config = ConfigDict(from_attributes=True)


class PassaporteUpdate(PassaporteBase):
    @field_validator('passaporte', 'visa', mode='before')
    @classmethod
    def normalizar_documento(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        return v or None


class PassaportePublic(PassaporteBase):
    id: int
    user_id: int


class TripPassaporteOut(BaseModel):
    trip_id: int
    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    saram: str | None
    telefone: str | None
    passaporte: PassaportePublic | None = None

    model_config = ConfigDict(from_attributes=True)
