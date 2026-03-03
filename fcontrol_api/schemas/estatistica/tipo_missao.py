import re

from pydantic import BaseModel, ConfigDict, field_validator


class TipoMissaoCreate(BaseModel):
    cod: str
    desc: str

    @field_validator('cod')
    @classmethod
    def validar_cod(cls, v: str) -> str:
        if not re.fullmatch(r'\d{2}[A-Za-z]{2}', v):
            msg = 'Formato invalido: 2 digitos + 2 letras (ex: 01AB)'
            raise ValueError(msg)
        return v.upper()


class TipoMissaoPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cod: str
    desc: str
