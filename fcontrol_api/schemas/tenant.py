from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from fcontrol_api.enums.cargo import CARGO_LABELS, CargoEnum
from fcontrol_api.enums.tema import TemaEnum
from fcontrol_api.schemas.organizacao import OrganizacaoOut
from fcontrol_api.schemas.users import UserPublic


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


class TenantCargoUpsert(BaseModel):
    """Define (ou troca) o titular de um cargo da org."""

    user_id: int


class TenantCargoOut(BaseModel):
    """Titular de um cargo, com o usuário completo para o documento.

    O consumidor (geração de DOCX) monta a linha de assinatura a partir de
    `user.nome_completo`, `user.posto.mid` e `user.quadro` — nada de texto
    congelado. `label` é o rótulo impresso abaixo da assinatura.
    """

    model_config = ConfigDict(from_attributes=True)

    cargo: CargoEnum
    user: UserPublic

    @computed_field
    @property
    def label(self) -> str:
        return CARGO_LABELS[self.cargo]
