from typing import Optional

from pydantic import BaseModel, ConfigDict


class EtiquetaSchema(BaseModel):
    """Schema para serialização de etiquetas"""

    id: Optional[int] = None
    nome: str
    cor: str
    descricao: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
