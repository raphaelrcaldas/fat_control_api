from pydantic import BaseModel, ConfigDict


class CidadeSchema(BaseModel):
    codigo: int
    nome: str
    uf: str
    model_config = ConfigDict(from_attributes=True)
