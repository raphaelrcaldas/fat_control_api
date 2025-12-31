from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Etiqueta(Base):
    """Modelo para etiquetas de uso geral (OM, etc) no schema public"""

    __tablename__ = 'etiquetas'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    cor: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # Hex color #RRGGBB
    descricao: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Relacionamento back-reference para Ordens de Missão
    ordens = relationship(
        'OrdemMissao',
        secondary='ordem_etiqueta',
        back_populates='etiquetas',
        init=False,
        default_factory=list,
    )
