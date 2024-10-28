from typing import Literal

from pydantic import BaseModel

opers = Literal['op', 'in', 'al']
funcs = Literal['pil', 'mc', 'lm', 'oe', 'os', 'tf', 'ml']
proj = Literal['kc-390']


class FuncSchema(BaseModel):
    func: funcs
    oper: opers
    proj: proj


class FuncPublic(FuncSchema):
    id: int
