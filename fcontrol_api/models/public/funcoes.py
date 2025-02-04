from datetime import date

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from .. import Base


class Funcao(Base):
    __tablename__ = 'trip_funcs'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))
    func: Mapped[str]
    oper: Mapped[str]
    proj: Mapped[str]
    data_op: Mapped[date] = mapped_column(nullable=True)
