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
        *(
            CheckConstraint(
                f'm{i} >= 0 AND m{i} % 5 = 0',
                name=f'ck_aloc_m{i}',
            )
            for i in range(1, 13)
        ),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    esfaer_id: Mapped[int] = mapped_column(ForeignKey(EsforcoAereo.id))
    ano_ref: Mapped[int]
    alocado: Mapped[int]
    m1: Mapped[int] = mapped_column(SmallInteger, default=0)
    m2: Mapped[int] = mapped_column(SmallInteger, default=0)
    m3: Mapped[int] = mapped_column(SmallInteger, default=0)
    m4: Mapped[int] = mapped_column(SmallInteger, default=0)
    m5: Mapped[int] = mapped_column(SmallInteger, default=0)
    m6: Mapped[int] = mapped_column(SmallInteger, default=0)
    m7: Mapped[int] = mapped_column(SmallInteger, default=0)
    m8: Mapped[int] = mapped_column(SmallInteger, default=0)
    m9: Mapped[int] = mapped_column(SmallInteger, default=0)
    m10: Mapped[int] = mapped_column(SmallInteger, default=0)
    m11: Mapped[int] = mapped_column(SmallInteger, default=0)
    m12: Mapped[int] = mapped_column(SmallInteger, default=0)


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
