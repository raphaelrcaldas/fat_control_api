from typing import Optional

from pydantic import BaseModel, ConfigDict


class EtiquetaBase(BaseModel):
    nome: str
    cor: str
    descricao: Optional[str] = None


class EtiquetaCreate(EtiquetaBase):
    pass


class EtiquetaUpdate(BaseModel):
    nome: Optional[str] = None
    cor: Optional[str] = None
    descricao: Optional[str] = None


class EtiquetaSchema(EtiquetaBase):
    """Schema para serialização de etiquetas (output)"""

    id: int

    model_config = ConfigDict(from_attributes=True)


class EtiquetaInput(EtiquetaBase):
    """Schema para criação/atualização de etiquetas (input)"""

    id: Optional[int] = None
