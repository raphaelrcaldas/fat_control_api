from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.posto_grad import PostoGradSchema


class SoldoCreate(BaseModel):
    pg: str = Field(..., min_length=1, max_length=10)
    data_inicio: date
    data_fim: date | None = None
    valor: float = Field(..., gt=0)


class SoldoUpdate(BaseModel):
    pg: str | None = Field(None, min_length=1, max_length=10)
    data_inicio: date | None = None
    data_fim: date | None = None
    valor: float | None = Field(None, gt=0)


class SoldoPublic(BaseModel):
    id: int
    pg: str
    data_inicio: date
    data_fim: date | None
    valor: float
    posto_grad: PostoGradSchema | None = None

    model_config = ConfigDict(from_attributes=True)


class SoldoStats(BaseModel):
    total: int
    min_valor: float | None
    max_valor: float | None
