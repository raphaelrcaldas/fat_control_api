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


class EsfAerResumoResponse(BaseModel):
    items: list[EsfAerResumoItem]
    total_alocado: int
    total_voado: int
    total_saldo: int
    total_meses: list[int]
