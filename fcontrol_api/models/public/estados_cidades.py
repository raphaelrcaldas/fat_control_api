from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Estado(Base):
    __tablename__ = 'estados'

    codigo_uf: Mapped[int]
    nome: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str] = mapped_column(primary_key=True)


class Cidade(Base):
    __tablename__ = 'cidades'

    codigo: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(nullable=False)
    uf: Mapped[str] = mapped_column(ForeignKey('estados.uf'), nullable=False)


class GrupoLocEsp(Base):
    __tablename__ = 'grupos_loc_esp'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    cidade_id: Mapped[int] = mapped_column(ForeignKey(Cidade.codigo))
    grupo: Mapped[int] = mapped_column(nullable=False)
