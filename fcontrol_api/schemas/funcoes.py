from datetime import date
from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, ConfigDict

opers = Literal['op', 'in', 'al']
funcs = Literal['mc', 'lm', 'oe', 'os', 'tf', 'ml']
proj = Literal['kc-390']


class BaseFunc(BaseModel):
    func: funcs
    oper: opers
    proj: proj
    data_op: Annotated[date | None, Body()]
    model_config = ConfigDict(from_attributes=True)


class FuncSchema(BaseFunc):
    trip_id: int


class FuncPublic(FuncSchema):
    id: int


class FuncUpdate(BaseModel):
    oper: opers
    data_op: Annotated[date | None, Body()]
