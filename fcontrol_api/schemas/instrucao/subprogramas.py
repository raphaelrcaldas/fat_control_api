import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Doutrina, nao varia por unidade — por isso lista fechada aqui, e nao
# tabela de apoio como aconteceu com as funcoes de tripulante.
TipoSubprograma = Literal['Formação', 'Manutenção', 'Especialização']

CODIGO_RE = re.compile(r'^[A-Z]{4}-\d{2}$')


class SubprogramaBase(BaseModel):
    codigo: str = Field(min_length=7, max_length=7, examples=['SPFO-01'])
    descricao: str = Field(min_length=3, max_length=120)
    tipo: TipoSubprograma
    func: str = Field(min_length=2, max_length=3)
    observacoes: str | None = None

    @field_validator('codigo')
    @classmethod
    def codigo_no_formato(cls, valor: str) -> str:
        codigo = valor.strip().upper()
        if not CODIGO_RE.match(codigo):
            raise ValueError(
                'Código deve ter 4 letras, hífen e 2 dígitos (ex.: SPFO-01)'
            )
        return codigo

    @field_validator('descricao')
    @classmethod
    def descricao_sem_espaco_sobrando(cls, valor: str) -> str:
        return valor.strip()

    @field_validator('observacoes')
    @classmethod
    def observacoes_vazias_viram_nulo(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpo = valor.strip()
        return limpo or None


class SubprogramaCreate(SubprogramaBase):
    pass


class SubprogramaUpdate(SubprogramaBase):
    pass


class SubprogramaOut(SubprogramaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
