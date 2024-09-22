from pydantic import BaseModel


class FuncPublic(BaseModel):
    func: str
    oper: str
    proj: str
