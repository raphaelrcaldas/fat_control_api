from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Identity,
    SmallInteger,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EsforcoAereo(Base):
    __tablename__ = 'esf_aer'

    id: Mapped[int] = mapped_column(
        SmallInteger, Identity(), init=False, primary_key=True
    )
    tipo: Mapped[str]
    modelo: Mapped[str]
    grupo: Mapped[str]
    prog: Mapped[str]
    sub_prog: Mapped[str | None] = mapped_column(nullable=True)
    aplicacao: Mapped[str | None] = mapped_column(nullable=True)
    descricao: Mapped[str] = mapped_column(
        Computed(
            "grupo || ' ' || prog || COALESCE(' ' || sub_prog, '')"
            " || COALESCE(' ' || aplicacao, '')",
            persisted=True,
        ),
        init=False,
    )


class EsfAerAloc(Base):
    __tablename__ = 'esf_aer_alocado'
    __table_args__ = (
        CheckConstraint('alocado >= 0', name='ck_alocado_aloc_min'),
        CheckConstraint('alocado % 5 = 0', name='ck_alocado_multiplo_5'),
        CheckConstraint('ano_ref >= 2020', name='ck_alocado_anoref_min'),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    esfaer_id: Mapped[int] = mapped_column(ForeignKey(EsforcoAereo.id))
    ano_ref: Mapped[int]
    alocado: Mapped[int]


class EsfAerAlocHist(Base):
    __tablename__ = 'esf_aer_aloc_hist'
    __table_args__ = (
        CheckConstraint('aloc_hist >= 0', name='ck_aloc_hist_min'),
        CheckConstraint('aloc_hist % 5 = 0', name='ck_aloc_hist_multiplo_5'),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    esf_aer_aloc_id: Mapped[int] = mapped_column(ForeignKey(EsfAerAloc.id))
    aloc_hist: Mapped[int]
    timestamp: Mapped[datetime]
