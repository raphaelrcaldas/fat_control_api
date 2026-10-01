from typing import Annotated, Self

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NomeImportacao = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
TextoImportacao = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=200)
]


class EsfAerItem(BaseModel):
    """Item simplificado para selects de formulario."""

    id: int
    descricao: str


class EsfAerResumoItem(BaseModel):
    id: int
    descricao: str
    grupo: str
    alocado: int
    voado: int
    saldo: int
    meses_sagem: list[int]
    meses_voados: list[int]


class EsfAerUpdateItem(BaseModel):
    """Item de importacao de Esforco Aereo."""

    tipo: NomeImportacao
    modelo: NomeImportacao
    grupo: NomeImportacao
    programa: NomeImportacao
    subprograma: TextoImportacao
    aplicacao: TextoImportacao
    horas_alocadas: int = Field(ge=0, multiple_of=5, le=2_147_483_647)
    meses_sagem: list[int] = [0] * 12

    @field_validator('meses_sagem')
    @classmethod
    def validate_meses(cls, v: list[int]) -> list[int]:
        if len(v) != 12:
            msg = 'meses_sagem deve ter exatamente 12 elementos'
            raise ValueError(msg)
        if any(m < 0 for m in v):
            msg = 'valores mensais devem ser >= 0'
            raise ValueError(msg)
        if any(m > 32767 for m in v):
            msg = 'valores mensais devem ser <= 32767'
            raise ValueError(msg)
        if any(m % 5 != 0 for m in v):
            msg = 'valores mensais devem ser multiplos de 5'
            raise ValueError(msg)
        return v


class EsfAerUpdateRequest(BaseModel):
    """Payload de importacao em lote de Esforco Aereo."""

    ano_ref: int = Field(ge=2020, le=9999)
    items: list[EsfAerUpdateItem] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def validate_itens_unicos(self) -> Self:
        posicoes: dict[tuple[str, ...], int] = {}
        repetidas: list[str] = []
        for posicao, item in enumerate(self.items, start=1):
            chave = (
                item.tipo,
                item.modelo,
                item.grupo,
                item.programa,
                item.subprograma,
                item.aplicacao,
            )
            if chave in posicoes:
                repetidas.append(f'{posicoes[chave]} e {posicao}')
            else:
                posicoes[chave] = posicao
        if repetidas:
            msg = 'Itens duplicados nas posições: ' + '; '.join(repetidas)
            raise ValueError(msg)
        return self


class EsfAerDiffRow(BaseModel):
    """Linha de comparacao antes/depois."""

    descricao: str
    antes: int | None
    depois: int | None


class EsfAerImportResponse(BaseModel):
    """Resumo da importacao de Esforco Aereo."""

    ano_ref: int
    rows: list[EsfAerDiffRow]
    total_antes: int
    total_depois: int


class HistPoint(BaseModel):
    """Ponto da timeline de alocacao (data no formato YYYY-MM-DD)."""

    data: str
    alocado: int
    delta: int


class HistPrograma(BaseModel):
    """Historico de alocacao de um programa de Esforco Aereo."""

    esfaer_id: int
    descricao: str
    nome: str
    grupo: str
    atual: int
    timeline: list[HistPoint]


class HistTotal(BaseModel):
    """Serie agregada (carry-forward) de todos os programas."""

    atual: int
    timeline: list[HistPoint]


class EsfAerHistorico(BaseModel):
    """Historico de alocacoes de Esforco Aereo no ano."""

    ano_ref: int
    programas: list[HistPrograma]
    total: HistTotal


class EsfAerResumoResponse(BaseModel):
    items: list[EsfAerResumoItem]
    total_alocado: int
    total_voado: int
    total_saldo: int
    total_meses_sagem: list[int]
    total_meses_voados: list[int]
