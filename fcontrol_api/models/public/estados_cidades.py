from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Estados(Base):
    __tablename__ = 'estados'

    codigo_uf: Mapped[int]
    nome: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str] = mapped_column(primary_key=True)


class Cidades(Base):
    __tablename__ = 'cidades'

    codigo: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str] = mapped_column(
        ForeignKey('estados.uf'), nullable=False
    )
