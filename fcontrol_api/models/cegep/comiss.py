from datetime import date

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.users import User

from .base import Base


class Comissionamento(Base):
    __tablename__ = 'comissionamento'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    status: Mapped[str]
    dep: Mapped[bool]
    cache_calc: Mapped[dict] = mapped_column(
        JSONB, server_default='{}', nullable=False, init=False
    )

    data_ab: Mapped[date]
    qtd_aj_ab: Mapped[float]
    valor_aj_ab: Mapped[float]

    data_fc: Mapped[date]
    qtd_aj_fc: Mapped[float]
    valor_aj_fc: Mapped[float]

    dias_cumprir: Mapped[int] = mapped_column(nullable=True)

    doc_prop: Mapped[str]
    doc_aut: Mapped[str]
    doc_enc: Mapped[str] = mapped_column(nullable=True)

    user = relationship(
        User, backref='comissionamento', lazy='selectin', uselist=False
    )
