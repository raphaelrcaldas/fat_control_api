from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Tripulante(Base):
    __tablename__ = 'tripulantes'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    trig: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool]
    uae: Mapped[str]
    user = relationship(
        'User', backref='tripulantes', lazy='selectin', uselist=False
    )
    funcs = relationship(
        'Funcao', backref='tripulantes', lazy='selectin', uselist=True
    )
