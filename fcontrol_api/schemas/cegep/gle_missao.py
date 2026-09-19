from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from fcontrol_api.schemas.cegep.gle_calculo import TrechoCalculado


class TrechoMissaoIn(BaseModel):
    loc_esp_id: int
    chegada: datetime
    afastamento: datetime

    @model_validator(mode='after')
    def valida_periodo(self):
        if self.afastamento <= self.chegada:
            raise ValueError('O afastamento deve ser posterior à chegada.')
        return self


class MissaoGleBase(BaseModel):
    descricao: str
    obs: str | None = None

    @field_validator('descricao')
    @classmethod
    def sem_espaco_sobrando(cls, v: str) -> str:
        # O corte vem antes da checagem: `min_length` no `Field` aprovaria
        # "   " (3 caracteres), o strip gravaria string vazia e o mesmo
        # schema, agora como saída, estouraria 500 na leitura seguinte.
        cortado = v.strip()
        if not cortado:
            raise ValueError('Informe a descrição.')
        return cortado


class MissaoGleCreate(MissaoGleBase):
    # Missão sem trecho ou sem militar não apura nada: o `percentual` sairia
    # vazio e a linha da lista, sem período. Não existe rascunho — quem abriu
    # a tela e desistiu simplesmente não salva.
    trechos: list[TrechoMissaoIn] = Field(min_length=1)
    militares_ids: list[int] = Field(min_length=1)

    @field_validator('militares_ids')
    @classmethod
    def sem_repetidos(cls, v: list[int]) -> list[int]:
        if len(set(v)) != len(v):
            raise ValueError('Militar repetido na lista.')
        return v


class MissaoGleUpdate(MissaoGleCreate):
    pass


class MilitarMissaoOut(BaseModel):
    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    saram: str
    soldo: Decimal
    valor: Decimal


class MissaoGleOut(MissaoGleBase):
    id: int
    created_at: datetime
    multiplicador: Decimal
    percentual: str
    trechos: list[TrechoCalculado]
    militares: list[MilitarMissaoOut]


class MissaoGleResumo(BaseModel):
    """Linha da lista: o suficiente para reconhecer e escolher a missão."""

    id: int
    descricao: str
    created_at: datetime
    total_trechos: int
    total_militares: int
    percentual: str
    # Primeiro e último dia de permanência. Nunca nulos: a missão só existe
    # com pelo menos um trecho.
    primeira_data: datetime
    ultima_data: datetime
    localidades: list[str]
