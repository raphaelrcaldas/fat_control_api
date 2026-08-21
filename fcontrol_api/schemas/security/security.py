from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.users import UserPublic

# Nome de recurso: `modulo.recurso[.subrecurso...]`, sem teto de níveis.
# Underscore junta palavras de um mesmo conceito (`ordem_missao`); o ponto
# separa níveis de hierarquia (`ops` › `ordem_missao` › `status`). Recurso
# transversal fica na raiz (`users`). O identificador efetivo de uma
# autorização é `<recurso>.<permissão>`, que é o que a API já devolve em
# 'Permissão negada: ops.ordem_missao.status.update'.
#
# Sem esta validação a base acumulou quatro convenções ao mesmo tempo
# (`cartoes-saude`, `dados_bancarios`, `comiss.propostas`, `sebo`) e três
# nomes escritos errado no front, que o PermBased engolia em silêncio.
RESOURCE_PATTERN = r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'
PERMISSION_PATTERN = r'^[a-z][a-z0-9_]*$'


# Resources
class ResourceBase(BaseModel):
    name: str
    description: str


class ResourceSchema(ResourceBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# Permissions
class PermissionBase(BaseModel):
    resource_id: int
    name: str
    description: str


class PermissionSchema(PermissionBase):
    id: int
    resource: ResourceSchema
    model_config = ConfigDict(from_attributes=True)


class PermissionDetailSchema(BaseModel):
    id: int
    resource: str
    action: str
    description: str
    model_config = ConfigDict(from_attributes=True)


class RoleSchema(BaseModel):
    id: int
    name: str = Field(..., min_length=1)
    description: Optional[str] = None


class RoleDetailSchema(RoleSchema):
    permissions: list[PermissionDetailSchema]


class UserRoleSchema(BaseModel):
    id: Optional[int] = None
    user_id: int
    role_id: int
    # NULL = escopo de sistema (admin global); preenchido = restrito a org.
    organizacao_id: Optional[str] = None


class UserWithRole(BaseModel):
    role: RoleSchema
    user: UserPublic
    organizacao_id: Optional[str] = None


# Create/Update schemas
class ResourceCreate(BaseModel):
    name: str = Field(..., min_length=1, pattern=RESOURCE_PATTERN)
    description: str = Field(..., min_length=1)


class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, pattern=RESOURCE_PATTERN)
    description: str | None = None


class PermissionCreate(BaseModel):
    resource_id: int
    name: str = Field(..., min_length=1, pattern=PERMISSION_PATTERN)
    description: str = Field(..., min_length=1)


class PermissionUpdate(BaseModel):
    name: str | None = Field(default=None, pattern=PERMISSION_PATTERN)
    description: str | None = None


class RolePermissionAction(BaseModel):
    permission_id: int
