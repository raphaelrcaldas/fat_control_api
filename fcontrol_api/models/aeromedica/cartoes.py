from datetime import date

from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.users import User

from .base import Base


class CartaoSaude(Base):
    __tablename__ = 'cartoes_saude'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id), unique=True
    )
    cemal: Mapped[date | None]
    ag_cemal: Mapped[date | None]
    tovn: Mapped[date | None]
    imae: Mapped[date | None]
    prontuario: Mapped[str | None] = mapped_column(
        String(20), default=None
    )

    user = relationship(
        User,
        backref='cartao_saude',
        lazy='selectin',
        uselist=False,
    )
