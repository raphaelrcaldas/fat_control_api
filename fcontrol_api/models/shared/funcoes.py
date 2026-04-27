from datetime import date

from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Funcao(Base):
    __tablename__ = 'trip_funcs'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))
    func: Mapped[str] = mapped_column(String(3))
    oper: Mapped[str] = mapped_column(String(2))
    proj: Mapped[str]
    data_op: Mapped[date] = mapped_column(nullable=True)
