from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.shared.tenant import Tenant

from .base import Base


class OrcamentoAnual(Base):
    __tablename__ = 'orcamento_anual'
    __table_args__ = (
        UniqueConstraint(
            'uae', 'ano_ref', name='uq_orcamento_anual_uae_ano_ref'
        ),
        CheckConstraint(
            'abertura + fechamento = total',
            name='ck_orcamento_anual_soma_cotas',
        ),
        CheckConstraint('total >= 0', name='ck_orcamento_anual_total_pos'),
        CheckConstraint(
            'abertura >= 0', name='ck_orcamento_anual_abertura_pos'
        ),
        CheckConstraint(
            'fechamento >= 0',
            name='ck_orcamento_anual_fechamento_pos',
        ),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    # Escopo multi-tenant: FK cross-Base usa o objeto-Column
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            Tenant.organizacao_id,
            ondelete='RESTRICT',
            onupdate='CASCADE',
        ),
    )
    ano_ref: Mapped[int] = mapped_column(nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    abertura: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fechamento: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
