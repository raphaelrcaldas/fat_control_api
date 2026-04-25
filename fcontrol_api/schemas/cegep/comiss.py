from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.cegep.missoes import FragMisEmbed, FragMisSchema
from fcontrol_api.schemas.users import UserPublic


class ComissSchema(BaseModel):
    id: Optional[int] = None
    user_id: int
    status: str
    dep: bool = False

    data_ab: date
    qtd_aj_ab: float
    valor_aj_ab: float

    data_fc: date
    qtd_aj_fc: float
    valor_aj_fc: float

    dias_cumprir: int | None

    doc_prop: str
    doc_aut: str
    doc_enc: str | None

    model_config = ConfigDict(from_attributes=True)


class ComissLogOut(BaseModel):
    id: int
    user: UserPublic
    action: str
    before: dict | None
    after: dict | None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ComissPublic(BaseModel):
    """Comissionamento com dados de usuário e valores do cache."""

    id: int
    status: str
    dep: bool = False
    data_ab: date
    qtd_aj_ab: float
    valor_aj_ab: float
    data_fc: date
    qtd_aj_fc: float
    valor_aj_fc: float
    dias_cumprir: int | None = None
    doc_prop: str
    doc_aut: str
    doc_enc: str | None = None
    user: UserPublic
    dias_comp: float = 0
    diarias_comp: float = 0
    vals_comp: float = 0
    modulo: bool = False
    completude: float = 0
    missoes_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ComissDetail(ComissPublic):
    """ComissPublic com missões e histórico de auditoria."""

    missoes: list[FragMisEmbed] = []
    logs: list[ComissLogOut] = []


class ComissFechamento(BaseModel):
    soma: float
    previsao: float
    orcamento: float


class ComissAbertura(BaseModel):
    soma: float
    orcamento: float


class ComissSummaryTotal(BaseModel):
    soma_abertura: float
    soma_fechamento: float
    soma: float
    previsao: float
    orcamento: float


class ComissSummaryResponse(BaseModel):
    orcamento_id: int | None
    fechamento: ComissFechamento
    abertura: ComissAbertura
    total: ComissSummaryTotal
    comissionamentos: list[ComissPublic]


class ComissMissaoPreview(BaseModel):
    """Missão resumida usada no preview de exclusão de comissionamento."""

    id: int
    tipo_doc: str
    n_doc: int
    desc: str
    afast: datetime
    regres: datetime


class ComissDeletePreview(BaseModel):
    missoes_count: int
    missoes: list[ComissMissaoPreview]


class ComissOutSchema(ComissSchema):
    dias_cumpridos: int = 0
    user: UserPublic
    missoes: list[FragMisSchema] = []
