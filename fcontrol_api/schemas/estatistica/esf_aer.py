from pydantic import BaseModel, field_validator


class EsfAerItem(BaseModel):
    """Item simplificado para selects de formulario."""

    id: int
    descricao: str


class EsfAerResumoItem(BaseModel):
    id: int
    descricao: str
    alocado: int
    voado: int
    saldo: int
    meses_sagem: list[int]
    meses_voados: list[int]


class EsfAerUpdateItem(BaseModel):
    """Item de importacao de Esforco Aereo."""

    tipo: str
    modelo: str
    grupo: str
    programa: str
    subprograma: str
    aplicacao: str
    horas_alocadas: int
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
        return v


class EsfAerUpdateRequest(BaseModel):
    """Payload de importacao em lote de Esforco Aereo."""

    ano_ref: int
    items: list[EsfAerUpdateItem]


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


class EsfAerResumoResponse(BaseModel):
    items: list[EsfAerResumoItem]
    total_alocado: int
    total_voado: int
    total_saldo: int
    total_meses_sagem: list[int]
    total_meses_voados: list[int]
