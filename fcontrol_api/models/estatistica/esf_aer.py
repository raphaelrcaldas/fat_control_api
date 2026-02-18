from sqlalchemy import Identity
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EsforcoAereo(Base):
    __tablename__ = 'esf_aer'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    tipo: Mapped[str]
    modelo: Mapped[str]
    grupo: Mapped[str]
    prog: Mapped[str]
    sub_prog: Mapped[str]
    aplicacao: Mapped[str]
