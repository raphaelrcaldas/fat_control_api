from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.cegep.missoes import FragMisSchema
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


class ComissOutSchema(ComissSchema):
    dias_cumpridos: int = 0
    user: UserPublic
    missoes: list[FragMisSchema] = []
