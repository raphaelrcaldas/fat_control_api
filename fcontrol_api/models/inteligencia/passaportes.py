from datetime import date

from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.users import User

from .base import Base


class Passaporte(Base):
    __tablename__ = 'passaportes'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), unique=True)
    passaporte: Mapped[str | None] = mapped_column(String(20))
    validade_passaporte: Mapped[date | None]
    visa: Mapped[str | None] = mapped_column(String(20))
    validade_visa: Mapped[date | None]

    user = relationship(
        User,
        backref='passaporte_registro',
        lazy='selectin',
        uselist=False,
    )
