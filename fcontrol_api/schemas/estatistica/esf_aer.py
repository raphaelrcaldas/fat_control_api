from pydantic import BaseModel


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
    meses: list[int]


class EsfAerUpdateItem(BaseModel):
    """Item de importacao de Esforco Aereo."""

    tipo: str
    modelo: str
    grupo: str
    programa: str
    subprograma: str
    aplicacao: str
    horas_alocadas: int


class EsfAerUpdateRequest(BaseModel):
    """Payload de importacao em lote de Esforco Aereo."""

    ano_ref: int
    items: list[EsfAerUpdateItem]


class EsfAerDiffRow(BaseModel):
    """Linha de comparacao antes/depois."""

    descricao: str
    antes: int
    depois: int


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
    total_meses: list[int]
