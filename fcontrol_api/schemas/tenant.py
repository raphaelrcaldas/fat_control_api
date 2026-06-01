from datetime import datetime

from pydantic import BaseModel, ConfigDict

from fcontrol_api.schemas.organizacao import OrganizacaoOut


class TenantCreate(BaseModel):
    """Registra uma organização do diretório como cliente da plataforma."""

    organizacao_id: str


class TenantUpdate(BaseModel):
    """Ativa/desativa um tenant na plataforma."""

    active: bool


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organizacao_id: str
    active: bool
    created_at: datetime
    organizacao: OrganizacaoOut
