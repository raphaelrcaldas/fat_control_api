from datetime import date, datetime
from typing import Annotated

from fastapi import Body
from pydantic import BaseModel, ConfigDict

from fcontrol_api.enums.indisp import IndispEnum
from fcontrol_api.schemas.funcoes import BaseFunc
from fcontrol_api.schemas.users import UserPublic


class BaseIndisp(BaseModel):
    date_start: Annotated[date | None, Body()] = None
    date_end: Annotated[date | None, Body()] = None
    mtv: IndispEnum | None = None
    obs: str | None = None


class IndispSchema(BaseModel):
    user_id: int
    date_start: Annotated[date, Body()]
    date_end: Annotated[date, Body()]
    mtv: IndispEnum
    obs: str


class IndispOut(IndispSchema):
    id: int
    created_at: Annotated[datetime, Body()]
    updated_at: Annotated[datetime | None, Body()] = None
    deleted_at: Annotated[datetime | None, Body()] = None
    user_created: UserPublic
    model_config = ConfigDict(from_attributes=True)


class IndispTripInfo(BaseFunc):
    """Dados do tripulante no contexto de indisponibilidades da escala.

    A função (func/oper/proj/data_op) vem achatada de BaseFunc — é 1:1 no
    próprio tripulante.
    """

    id: int
    trig: str
    user: UserPublic
    cemal: date | None = None
    data_ult_voo: date | None = None


class IndispCrewEntry(BaseModel):
    trip: IndispTripInfo
    indisps: list[IndispOut]
