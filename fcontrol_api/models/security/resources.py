from sqlalchemy import ForeignKey, Identity, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.models.shared.users import User

from .base import Base


class Resources(Base):
    __tablename__ = 'resources'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    name: Mapped[str]
    description: Mapped[str]


class Permissions(Base):
    __tablename__ = 'permissions'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    resource_id: Mapped[int] = mapped_column(
        ForeignKey('security.resources.id')
    )
    name: Mapped[str]
    description: Mapped[str]
    resource: Mapped[Resources] = relationship(
        'Resources',
        backref='permissions',
        lazy='selectin',
        uselist=False,
        init=False,
    )


class RolePermissions(Base):
    __tablename__ = 'role_permissions'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    role_id: Mapped[int] = mapped_column(ForeignKey('security.roles.id'))
    permission_id: Mapped[int] = mapped_column(
        ForeignKey('security.permissions.id')
    )
    permission: Mapped[Permissions] = relationship(
        'Permissions',
        backref='role_permissions',
        lazy='selectin',
        uselist=False,
        init=False,
    )


class Roles(Base):
    __tablename__ = 'roles'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    name: Mapped[str]
    description: Mapped[str]
    permissions: Mapped[list[RolePermissions]] = relationship(
        'RolePermissions',
        backref='roles',
        lazy='selectin',
        uselist=True,
        init=False,
        default_factory=list,
    )


class UserRole(Base):
    __tablename__ = 'user_roles'
    # Um usuário tem no máximo 1 role por org (NULL = sistema). NULLS NOT
    # DISTINCT garante que isso valha também para o vínculo de sistema.
    __table_args__ = (
        UniqueConstraint(
            'user_id',
            'organizacao_id',
            name='uq_user_roles_user_org',
            postgresql_nulls_not_distinct=True,
        ),
        {'schema': 'security'},
    )

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    role_id: Mapped[int] = mapped_column(ForeignKey('security.roles.id'))
    organizacao_id: Mapped[str | None] = mapped_column(
        ForeignKey(Tenant.organizacao_id), nullable=True, default=None
    )
    role: Mapped[Roles] = relationship(
        Roles, backref='user_roles', lazy='selectin', uselist=False, init=False
    )
    user: Mapped[User] = relationship(
        User, backref='user_roles', lazy='raise', uselist=False, init=False
    )
