from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
    relationship,
)

from ..public.users import User


class Base(MappedAsDataclass, DeclarativeBase):
    """subclasses will be converted to dataclasses"""

    __table_args__ = {'schema': 'security'}


class Resources(Base):
    __tablename__ = 'resources'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    name: Mapped[str]
    description: Mapped[str]


class Permissions(Base):
    __tablename__ = 'permissions'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey('security.resources.id')
    )
    name: Mapped[str]
    description: Mapped[str]


class Roles(Base):
    __tablename__ = 'roles'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    name: Mapped[str]
    description: Mapped[str]


class RolePermissions(Base):
    __tablename__ = 'role_permissions'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    role_id: Mapped[int] = mapped_column(ForeignKey('security.roles.id'))
    permission_id: Mapped[int] = mapped_column(
        ForeignKey('security.permissions.id')
    )


class UserRoles(Base):
    __tablename__ = 'user_roles'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    role_id: Mapped[int] = mapped_column(ForeignKey('security.roles.id'))
