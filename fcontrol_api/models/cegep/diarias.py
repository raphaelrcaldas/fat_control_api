from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.shared.estados_cidades import Cidade
from fcontrol_api.models.shared.posto_grad import PostoGrad

from .base import Base


class GrupoCidade(Base):
    __tablename__ = 'grupos_cidade'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    grupo: Mapped[int] = mapped_column(nullable=False)
    cidade_id: Mapped[int] = mapped_column(ForeignKey(Cidade.codigo))


class GrupoPg(Base):
    __tablename__ = 'grupos_pg'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    grupo: Mapped[int] = mapped_column(nullable=False)
    pg_short: Mapped[int] = mapped_column(ForeignKey(PostoGrad.short))


class DiariaValor(Base):
    __tablename__ = 'valor_diarias'
    __table_args__ = (
        CheckConstraint(
            'valor >= 0', name='ck_valor_diarias_valor_nao_negativo'
        ),
        CheckConstraint(
            'data_fim IS NULL OR data_inicio < data_fim',
            name='ck_valor_diarias_data_inicio_antes_fim',
        ),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    grupo_pg: Mapped[int]
    grupo_cid: Mapped[int]
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    data_inicio: Mapped[date] = mapped_column(nullable=False)
    data_fim: Mapped[date] = mapped_column(nullable=True)
