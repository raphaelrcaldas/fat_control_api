"""Modelos para Ordem de Missão (OM)"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Identity,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Etiqueta(Base):
    """Modelo para etiquetas de Ordens de Missão"""

    __tablename__ = 'om_etiquetas'

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
        secondary='om_etiqueta',
        back_populates='etiquetas',
        init=False,
        default_factory=list,
    )


class OrdemEtiqueta(Base):
    """Tabela associativa Many-to-Many entre OrdemMissao e Etiqueta"""

    __tablename__ = 'om_etiqueta'

    ordem_id: Mapped[int] = mapped_column(
        ForeignKey('om_ordens_missao.id', ondelete='CASCADE'),
        primary_key=True,
    )
    etiqueta_id: Mapped[int] = mapped_column(
        ForeignKey('om_etiquetas.id', ondelete='CASCADE'),
        primary_key=True,
    )


class OrdemMissao(Base):
    """Ordem de Missão principal"""

    __tablename__ = 'om_ordens_missao'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    numero: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=False
    )
    matricula_anv: Mapped[int] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    projeto: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    campos_especiais: Mapped[list] = mapped_column(JSONB)
    uae: Mapped[str] = mapped_column(String(20), nullable=False)
    esf_aer: Mapped[int] = mapped_column(nullable=False, default=0)
    doc_ref: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    data_saida: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        init=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
    )

    # Relacionamentos (carregados automaticamente com selectin)
    etapas: Mapped[list['OrdemEtapa']] = relationship(
        'OrdemEtapa',
        lazy='selectin',
        cascade='all, delete-orphan',
        init=False,
    )
    tripulacao: Mapped[list['OrdemTripulacao']] = relationship(
        'OrdemTripulacao',
        lazy='selectin',
        cascade='all, delete-orphan',
        init=False,
    )
    user_created = relationship(
        'User',
        backref='ordens_criadas',
        lazy='selectin',
        foreign_keys=[created_by],
    )
    # Relacionamento many-to-many com etiquetas
    etiquetas: Mapped[list['Etiqueta']] = relationship(
        'Etiqueta',
        secondary='om_etiqueta',
        back_populates='ordens',
        lazy='selectin',
        init=False,
        default_factory=list,
    )


class OrdemEtapa(Base):
    """Etapa de uma Ordem de Missão"""

    __tablename__ = 'om_etapas'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    ordem_id: Mapped[int] = mapped_column(ForeignKey('om_ordens_missao.id'))
    dt_dep: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    origem: Mapped[str] = mapped_column(String(10))
    dest: Mapped[str] = mapped_column(String(10))
    dt_arr: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    alternativa: Mapped[str] = mapped_column(String(10))
    tvoo_etp: Mapped[int]
    tvoo_alt: Mapped[int]
    qtd_comb: Mapped[int]
    esf_aer: Mapped[str] = mapped_column(String(200))


class OrdemTripulacao(Base):
    """Tripulante alocado em uma Ordem de Missão"""

    __tablename__ = 'om_tripulacao'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    ordem_id: Mapped[int] = mapped_column(ForeignKey('om_ordens_missao.id'))
    tripulante_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))
    funcao: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # pil, mc, lm, tf, oe, os
    # Snapshot do posto/graduacao no momento da criacao da OM
    p_g: Mapped[str] = mapped_column(
        ForeignKey('posto_grad.short'), nullable=False
    )

    # Relacionamento com tripulante
    tripulante = relationship('Tripulante', lazy='selectin')
