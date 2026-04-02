from pydantic import BaseModel


class AnvMesData(BaseModel):
    """Horas voadas e pousos de um mes."""

    tvoo: int
    pousos: int


class AnvHorasRow(BaseModel):
    """Uma aeronave com dados mensais."""

    matricula: str
    meses: list[AnvMesData]
    total_tvoo: int
    total_pousos: int


class AnvHorasResponse(BaseModel):
    """Resposta completa com todas ANVs e totais."""

    items: list[AnvHorasRow]
    total_meses: list[AnvMesData]
    total_tvoo: int
    total_pousos: int
