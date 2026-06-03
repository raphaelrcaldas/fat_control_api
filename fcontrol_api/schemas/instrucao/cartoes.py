from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

NivelIdioma = Literal['A1', 'A2', 'B1', 'B2', 'C1', 'C2']


class CartoesBase(BaseModel):
    ptai_validade: date | None = None
    tai_s_validade: date | None = None
    tai_s1_validade: date | None = None
    cvi_validade: date | None = None
    hab_espanhol: NivelIdioma | None = None
    val_espanhol: date | None = None
    hab_ingles: NivelIdioma | None = None
    val_ingles: date | None = None

    model_config = ConfigDict(from_attributes=True)


class CartoesUpdate(CartoesBase):
    @model_validator(mode='after')
    def validade_requer_habilitacao(self) -> 'CartoesUpdate':
        if self.val_espanhol is not None and self.hab_espanhol is None:
            raise ValueError('val_espanhol requer hab_espanhol preenchido')
        if self.val_ingles is not None and self.hab_ingles is None:
            raise ValueError('val_ingles requer hab_ingles preenchido')
        return self


class CartoesPublic(CartoesBase):
    id: int
    user_id: int


class TripCartoesOut(BaseModel):
    trip_id: int
    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    saram: str | None
    cartao: CartoesPublic | None = None

    model_config = ConfigDict(from_attributes=True)
