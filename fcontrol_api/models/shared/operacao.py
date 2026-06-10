"""Modelos do módulo Operações / Manobras / Exercícios.

Agrupa várias `Etapa` (schema estatistica) sob um mesmo evento operacional
para consolidar estatísticas. Escopado por unidade tenant (`uae`).

Vínculo Operação→Etapa é 1:N: a FK `operacao_id` vive em `Etapa`
(uma etapa pertence a no máximo uma operação).
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.estatistica.etapa import Etapa

from .base import Base
from .estados_cidades import Cidade
from .users import User

TIPOS = ('operacao', 'manobra', 'exercicio')
STATUS = ('planejada', 'andamento', 'encerrada', 'cancelada')


class Operacao(Base):
    """Evento operacional (Operação, Manobra ou Exercício)."""

    __tablename__ = 'operacoes'
    __table_args__ = (
        UniqueConstraint('uae', 'nome', name='uq_operacao_uae_nome'),
        UniqueConstraint('uae', 'numero', name='uq_operacao_uae_numero'),
        CheckConstraint(
            'data_fim >= data_inicio',
            name='ck_operacao_periodo',
        ),
        CheckConstraint(
            "tipo IN ('operacao', 'manobra', 'exercicio')",
            name='ck_operacao_tipo',
        ),
        CheckConstraint(
            "status IN ('planejada', 'andamento', 'encerrada', 'cancelada')",
            name='ck_operacao_status',
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    numero: Mapped[int]
    nome: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20))
    cidade_id: Mapped[int] = mapped_column(ForeignKey('cidades.codigo'))
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            'tenants.organizacao_id',
            ondelete='RESTRICT',
            onupdate='CASCADE',
        ),
    )
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))

    documento_referencia: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    obs: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

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

    cidade: Mapped[Cidade] = relationship(Cidade, lazy='selectin', init=False)


class OperacaoEtapa(Base):
    """Vínculo Operação→Etapa (1:N).

    `etapa_id` é PK: cada etapa pertence a no máximo uma operação. A FK para
    `Etapa` (Base estatistica) usa o objeto-Column — direção feature→core; a
    Etapa não conhece operações.
    """

    __tablename__ = 'operacao_etapa'

    etapa_id: Mapped[int] = mapped_column(
        ForeignKey(
            Etapa.id,
            ondelete='CASCADE',
            name='fk_operacao_etapa_etapa',
        ),
        primary_key=True,
    )
    operacao_id: Mapped[int] = mapped_column(
        ForeignKey('operacoes.id', ondelete='CASCADE'),
        index=True,
    )


class OperacaoPessoal(Base):
    """Pessoal envolvido (lista única: tripulante de voo ou apoio)."""

    __tablename__ = 'operacao_pessoal'
    __table_args__ = (
        CheckConstraint(
            'data_regresso >= data_ingresso',
            name='ck_operacao_pessoal_periodo',
        ),
        UniqueConstraint(
            'operacao_id',
            'user_id',
            name='uq_operacao_pessoal_user',
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    operacao_id: Mapped[int] = mapped_column(
        ForeignKey('operacoes.id', ondelete='CASCADE'), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    func: Mapped[str] = mapped_column(String(80))
    om: Mapped[str] = mapped_column(String(60))
    data_ingresso: Mapped[date] = mapped_column(Date)
    data_regresso: Mapped[date] = mapped_column(Date)

    user: Mapped[User] = relationship(User, lazy='selectin', init=False)
