from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PostoGrad(Base):
    __tablename__ = 'posto_grad'

    ant: Mapped[int] = mapped_column(nullable=False)
    short: Mapped[str] = mapped_column(
        String(2), primary_key=True, nullable=False
    )
    mid: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    circulo: Mapped[str] = mapped_column(nullable=False)


class Soldo(Base):
    __tablename__ = 'soldos'
    # Alem das CheckConstraints abaixo, a tabela tem no banco uma constraint
    # EXCLUDE (btree_gist, DEFERRABLE) que impede faixas de vigencia
    # sobrepostas para o mesmo `pg` (ck_soldos_sem_sobreposicao). Ela vive
    # so na migration porque depende da extensao btree_gist e o autogenerate
    # do Alembic nao reflete ExcludeConstraint.
    __table_args__ = (
        CheckConstraint('valor >= 0', name='ck_soldos_valor_nao_negativo'),
        CheckConstraint(
            'data_fim IS NULL OR data_inicio < data_fim',
            name='ck_soldos_data_inicio_antes_fim',
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    pg: Mapped[str] = mapped_column(ForeignKey(PostoGrad.short))
    data_inicio: Mapped[date] = mapped_column(nullable=False)
    data_fim: Mapped[date] = mapped_column(nullable=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    posto_grad: Mapped[PostoGrad] = relationship(init=False, lazy='joined')
