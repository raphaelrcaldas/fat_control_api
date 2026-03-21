from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

NivelIdioma = Literal['A1', 'A2', 'B1', 'B2']


class IdiomasBase(BaseModel):
    ptai_validade: date | None = None
    tai_s_validade: date | None = None
    tai_s1_validade: date | None = None
    hab_espanhol: NivelIdioma | None = None
    val_espanhol: date | None = None
    hab_ingles: NivelIdioma | None = None
    val_ingles: date | None = None

    model_config = ConfigDict(from_attributes=True)


class IdiomasUpdate(IdiomasBase):
    @model_validator(mode='after')
    def validade_requer_habilitacao(self) -> 'IdiomasUpdate':
        if self.val_espanhol is not None and self.hab_espanhol is None:
            raise ValueError(
                'val_espanhol requer hab_espanhol preenchido'
            )
        if self.val_ingles is not None and self.hab_ingles is None:
            raise ValueError(
                'val_ingles requer hab_ingles preenchido'
            )
        return self


class IdiomasPublic(IdiomasBase):
    id: int
    user_id: int


class TripIdiomasOut(BaseModel):
    trip_id: int
    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    saram: str | None
    idiomas: IdiomasPublic | None = None

    model_config = ConfigDict(from_attributes=True)
