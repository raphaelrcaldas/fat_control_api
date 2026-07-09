from datetime import datetime

from pydantic import BaseModel, ConfigDict

from fcontrol_api.enums.tema import TemaEnum
from fcontrol_api.schemas.organizacao import OrganizacaoOut


class TenantCreate(BaseModel):
    """Registra uma organização do diretório como cliente da plataforma."""

    organizacao_id: str


class TenantUpdate(BaseModel):
    """Atualização parcial de um tenant (ativação e/ou tema)."""

    active: bool | None = None
    tema: TemaEnum | None = None


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organizacao_id: str
    active: bool
    tema: TemaEnum
    created_at: datetime
    organizacao: OrganizacaoOut
