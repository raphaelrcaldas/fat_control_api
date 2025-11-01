from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .users import UserPublic


class RoleSchema(BaseModel):
    id: int
    name: str = Field(..., min_length=1)
    description: Optional[str] = None


class UserRoleSchema(BaseModel):
    id: Optional[int] = None
    user_id: int
    role_id: int


class UserWithRole(BaseModel):
    role: RoleSchema
    user: UserPublic
