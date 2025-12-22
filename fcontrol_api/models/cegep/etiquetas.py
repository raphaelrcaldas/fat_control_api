from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class FragEtiqueta(Base):
    """Tabela associativa para relação many-to-many entre FragMis e Etiqueta"""
    __tablename__ = 'frag_etiqueta'

    frag_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.frag_mis.id', ondelete='CASCADE'), primary_key=True
    )
    etiqueta_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.etiqueta.id', ondelete='CASCADE'), primary_key=True
    )


class Etiqueta(Base):
    """Modelo para etiquetas de missões"""
    __tablename__ = 'etiqueta'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    cor: Mapped[str] = mapped_column(String(7), nullable=False)  # Hex color #RRGGBB
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    # Relação many-to-many com FragMis (definida via back_populates no FragMis)
    missoes = relationship(
        'FragMis',
        secondary='cegep.frag_etiqueta',
        back_populates='etiquetas',
        init=False,
        default_factory=list,
    )
