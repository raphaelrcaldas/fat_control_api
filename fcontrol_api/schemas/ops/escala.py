from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from fcontrol_api.enums.indisp import IndispEnum


class EscalaIndispInfo(BaseModel):
    mtv: IndispEnum
    date_start: date
    date_end: date

    model_config = ConfigDict(from_attributes=True)


class EscalaTripEntry(BaseModel):
    id: int
    user_id: int
    nome_guerra: str
    p_g: str
    trig: str | None
    func: str
    oper: str | None
    quads_count: int
    tvoo_year: int
    data_ult_voo: date | None
    cemal_date: date | None
    indisps: list[EscalaIndispInfo]


class EscalaFuncSection(BaseModel):
    func: str
    trips: list[EscalaTripEntry]


class EscalaResponse(BaseModel):
    date_start: date
    date_end: date
    sort: Literal['horas_voo', 'quads_asc']
    tipo_quad_id: int
    sections: list[EscalaFuncSection]
