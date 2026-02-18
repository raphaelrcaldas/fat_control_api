
from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.public.om import OrdemMissao

from .base import Base


class Missao(Base):
    __tablename__ = 'missao'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    om_id: Mapped[int] = mapped_column(ForeignKey(OrdemMissao.id))
    titulo: Mapped[str] = mapped_column(nullable=True)
    obs: Mapped[str] = mapped_column(nullable=True)
    # etapas = relationship(
    #     Etapas, backref='missao', lazy='selectin', uselist=True
    # )


class TipoMissao(Base):
    __tablename__ = 'tipo_missao'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    cod: Mapped[str] = mapped_column(nullable=False)
    desc: Mapped[str] = mapped_column(nullable=False)
