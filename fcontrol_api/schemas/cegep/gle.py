"""Schemas das localidades especiais (GLE).

`grupo` trafega como inteiro (1 = A, 2 = B), espelhando a coluna. A
conversao para letra e responsabilidade da tela: o usuario fala em
"grupo A", nunca em "grupo 1".
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Espelham os CheckConstraint de `grupos_loc_esp` e `loc_esp_icao`.
GRUPO_A = 1
GRUPO_B = 2
FUSO_MIN = -5
FUSO_MAX = 0


class LocEspBase(BaseModel):
    cidade_id: int
    grupo: int = Field(ge=GRUPO_A, le=GRUPO_B)
    fuso: int = Field(ge=FUSO_MIN, le=FUSO_MAX)


class LocEspCreate(LocEspBase):
    """Criacao: a lista de ICAOs vem junto, como parte da localidade."""

    icaos: list[str] = Field(default_factory=list)

    @field_validator('icaos')
    @classmethod
    def normaliza_icaos(cls, valor: list[str]) -> list[str]:
        """Normaliza para maiusculas e recusa duplicata no proprio payload.

        O unique do banco pega duplicata entre localidades; dentro de uma
        mesma lista ele so dispararia no flush, com erro opaco.
        """
        icaos = [item.strip().upper() for item in valor]
        for icao in icaos:
            if len(icao) != 4 or not icao.isalpha() or not icao.isascii():
                raise ValueError(
                    f'ICAO inválido: {icao!r}. Use 4 letras (ex.: SBEG).'
                )
        if len(set(icaos)) != len(icaos):
            raise ValueError('ICAO repetido na mesma localidade')
        return icaos


class LocEspUpdate(LocEspCreate):
    """Update completo: os ICAOs enviados substituem os atuais."""


class CidadeResumo(BaseModel):
    """Cidade embutida na resposta, para a tela nao ter de resolver o id."""

    codigo: int
    nome: str
    uf: str

    model_config = ConfigDict(from_attributes=True)


class LocEspOut(LocEspBase):
    id: int
    cidade: CidadeResumo
    icaos: list[str]

    model_config = ConfigDict(from_attributes=True)
