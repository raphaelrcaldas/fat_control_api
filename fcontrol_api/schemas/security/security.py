from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from fcontrol_api.schemas.users import UserPublic


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


class UserWithRole(BaseModel):
    role: RoleSchema
    user: UserPublic


# Create/Update schemas
class ResourceCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class ResourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PermissionCreate(BaseModel):
    resource_id: int
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class PermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RolePermissionAction(BaseModel):
    permission_id: int
