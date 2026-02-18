from datetime import date, time

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .missao import Missao


class OIEtapa(Base):
    __tablename__ = 'oi_etapa'
    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(ForeignKey(Missao.id))
    esf_aer_id: Mapped[int] = mapped_column(ForeignKey(Missao.id))
    reg: Mapped[str]  # diurno/noturno/nvg
    tipo_missao_id: Mapped[str]  # 69tt/58tv


class Etapa(Base):
    __tablename__ = 'etapas'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    missao_id: Mapped[int] = mapped_column(ForeignKey(Missao.id))
    obs: Mapped[str] = mapped_column(nullable=True)

    data: Mapped[date]
    origem: Mapped[str]
    destino: Mapped[str]
    dep: Mapped[time]
    arr: Mapped[time]
    tvoo: Mapped[int]

    # ofrag
    pousos: Mapped[int]
    anv: Mapped[int]
    tow: Mapped[int]
    pax: Mapped[int]
    carga: Mapped[int]
    comb: Mapped[int]
    lub: Mapped[int]
    nivel: Mapped[int]

    sagem: Mapped[bool]
    parte1: Mapped[bool]
