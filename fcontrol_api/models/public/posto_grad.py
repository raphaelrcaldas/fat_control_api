from datetime import date

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PostoGrad(Base):
    __tablename__ = 'posto_grad'

    ant: Mapped[int] = mapped_column(nullable=False)
    short: Mapped[str] = mapped_column(primary_key=True, nullable=False)
    mid: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    circulo: Mapped[str] = mapped_column(nullable=False)


class Soldo(Base):
    __tablename__ = 'soldos'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    pg: Mapped[str] = mapped_column(ForeignKey(PostoGrad.short))
    data_inicio: Mapped[date] = mapped_column(nullable=False)
    data_fim: Mapped[date] = mapped_column(nullable=True)
    valor: Mapped[float] = mapped_column(nullable=False)
