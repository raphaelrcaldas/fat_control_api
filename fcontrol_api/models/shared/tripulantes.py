from datetime import date

from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.users import User

from .base import Base


class Tripulante(Base):
    __tablename__ = 'tripulantes'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    trig: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool]
    uae: Mapped[str] = mapped_column(
        ForeignKey(
            'tenants.organizacao_id',
            ondelete='RESTRICT',
            onupdate='CASCADE',
        )
    )
    func: Mapped[str] = mapped_column(
        String(3),
        ForeignKey(
            'funcoes.cod',
            onupdate='CASCADE',
            name='fk_tripulantes_func',
        ),
    )
    oper: Mapped[str] = mapped_column(String(2))
    proj: Mapped[str] = mapped_column(
        ForeignKey(
            'projetos_anvs.modelo',
            onupdate='CASCADE',
            name='fk_tripulantes_proj',
        )
    )
    data_op: Mapped[date | None] = mapped_column(nullable=True, default=None)

    user: Mapped[User] = relationship(
        User,
        init=False,
        backref='tripulantes',
        lazy='selectin',
        uselist=False,
    )
