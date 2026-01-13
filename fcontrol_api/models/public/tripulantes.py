from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.users import User

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

    user: Mapped[User] = relationship(
        User,
        init=False,
        backref='tripulantes',
        lazy='selectin',
        uselist=False,
    )
    funcs: Mapped[list[Funcao]] = relationship(
        Funcao,
        init=False,
        backref='tripulantes',
        lazy='selectin',
        uselist=True,
    )
