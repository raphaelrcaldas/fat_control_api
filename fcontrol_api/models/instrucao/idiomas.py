from datetime import date

from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.users import User

from .base import Base


class IdiomasHabilidade(Base):
    __tablename__ = 'idiomas_habilidades'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), unique=True)
    ptai_validade: Mapped[date | None]
    tai_s_validade: Mapped[date | None]
    tai_s1_validade: Mapped[date | None]
    hab_espanhol: Mapped[str | None] = mapped_column(String(2))
    val_espanhol: Mapped[date | None]
    hab_ingles: Mapped[str | None] = mapped_column(String(2))
    val_ingles: Mapped[date | None]

    user = relationship(
        User,
        backref='idiomas_habilidade',
        lazy='selectin',
        uselist=False,
    )
