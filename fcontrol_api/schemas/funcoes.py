from datetime import date
from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel

opers = Literal['op', 'in', 'al']
funcs = Literal['mc', 'lm', 'oe', 'os', 'tf', 'ml']
proj = Literal['kc-390']
uae = Literal['11gt']


class BaseFunc(BaseModel):
    func: funcs
    oper: opers
    proj: proj
    data_op: Annotated[date | None, Body()]


class FuncSchema(BaseFunc):
    trip_id: int


class FuncPublic(FuncSchema):
    id: int
