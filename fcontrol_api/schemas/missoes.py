from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.users import UserPublic


class CidadeSchema(BaseModel):
    codigo: int
    nome: str
    uf: str
    model_config = ConfigDict(from_attributes=True)


class PernoiteFragMis(BaseModel):
    id: Optional[int] = None
    frag_id: Optional[int] = None
    acrec_desloc: bool
    data_ini: date
    data_fim: date
    meia_diaria: bool
    obs: str
    cidade_id: int
    cidade: CidadeSchema
    model_config = ConfigDict(from_attributes=True)


class UserFragMis(BaseModel):
    id: Optional[int] = None
    frag_id: Optional[int] = None
    user_id: int
    p_g: str
    sit: str
    user: UserPublic

    model_config = ConfigDict(from_attributes=True)


class FragMisSchema(BaseModel):
    id: Optional[int] = None
    n_doc: int
    tipo_doc: str
    indenizavel: bool
    acrec_desloc: bool
    afast: datetime
    regres: datetime
    desc: str
    obs: str
    tipo: str
    pernoites: list[PernoiteFragMis]
    users: list[UserFragMis]
    custos: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)
