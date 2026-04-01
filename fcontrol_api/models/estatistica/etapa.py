from datetime import date, time

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Identity,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.public.aeronaves import Aeronave
from fcontrol_api.models.public.tripulantes import Tripulante

from .base import Base


class Missao(Base):
    __tablename__ = 'missao'

    id: Mapped[int] = mapped_column(
        SmallInteger,
        Identity(),
        init=False,
        primary_key=True,
    )
    titulo: Mapped[str | None] = mapped_column(nullable=True)
    obs: Mapped[str | None] = mapped_column(nullable=True)
    is_simulador: Mapped[bool] = mapped_column(
        default=False,
        server_default='false',
    )


class TipoMissao(Base):
    __tablename__ = 'tipo_missao'

    id: Mapped[int] = mapped_column(
        SmallInteger,
        Identity(),
        init=False,
        primary_key=True,
    )
    cod: Mapped[str] = mapped_column(String(4), nullable=False)
    desc: Mapped[str] = mapped_column(nullable=False)


class Etapa(Base):
    __tablename__ = 'etapas'
    __table_args__ = (
        CheckConstraint(
            'tvoo % 5 = 0',
            name='ck_etapa_tvoo_multiplo_5',
        ),
        CheckConstraint('tvoo >= 5', name='ck_etapa_tvoo_min'),
        CheckConstraint('pousos >= 0', name='ck_etapa_pousos_nn'),
        CheckConstraint('tow > 0', name='ck_etapa_tow_positivo'),
        CheckConstraint('pax >= 0', name='ck_etapa_pax_nn'),
        CheckConstraint('carga >= 0', name='ck_etapa_carga_nn'),
        CheckConstraint('comb > 0', name='ck_etapa_comb_nn'),
        CheckConstraint('lub >= 0', name='ck_etapa_lub_nn'),
        CheckConstraint(
            "nivel ~ '^[0-9]{3}$'",
            name='ck_etapa_nivel_fl',
        ),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    missao_id: Mapped[int] = mapped_column(ForeignKey(Missao.id))
    obs: Mapped[str | None] = mapped_column(nullable=True)

    data: Mapped[date]
    origem: Mapped[str] = mapped_column(String(4))
    destino: Mapped[str] = mapped_column(String(4))
    dep: Mapped[time]
    arr: Mapped[time]
    tvoo: Mapped[int] = mapped_column(
        SmallInteger,
        Computed(
            'CASE WHEN arr < dep '
            'THEN EXTRACT(EPOCH FROM '
            "(arr - dep + interval '1 day'))"
            '::integer / 60 '
            'ELSE EXTRACT(EPOCH FROM '
            '(arr - dep))::integer / 60 END',
            persisted=True,
        ),
        init=False,
    )
    anv: Mapped[str] = mapped_column(ForeignKey(Aeronave.matricula))
    pousos: Mapped[int] = mapped_column(SmallInteger)

    # ofrag ?
    tow: Mapped[int | None] = mapped_column(nullable=True)
    pax: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    carga: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    comb: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    lub: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    nivel: Mapped[str | None] = mapped_column(String(3), nullable=True)

    sagem: Mapped[bool]
    parte1: Mapped[bool]


class OIEtapa(Base):
    __tablename__ = 'oi_etapa'
    __table_args__ = (
        CheckConstraint(
            'tvoo % 5 = 0',
            name='ck_oi_etapa_tvoo_multiplo_5',
        ),
        CheckConstraint('tvoo >= 5', name='ck_oi_etapa_tvoo_min'),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(
        ForeignKey(Etapa.id, ondelete='CASCADE')
    )
    esf_aer_id: Mapped[int] = mapped_column(ForeignKey(EsforcoAereo.id))
    tvoo: Mapped[int] = mapped_column(SmallInteger)
    reg: Mapped[str] = mapped_column(String(1))  # diurno(d)/noturno(n)/nvg(v)
    tipo_missao_id: Mapped[int] = mapped_column(ForeignKey(TipoMissao.id))


class TripEtapa(Base):
    __tablename__ = 'trip_etapa'
    __table_args__ = ({'schema': 'estatistica'},)

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(
        ForeignKey(Etapa.id, ondelete='CASCADE')
    )
    func: Mapped[str] = mapped_column(String(3))
    func_bordo: Mapped[str] = mapped_column(String(2))
    trip_id: Mapped[int] = mapped_column(ForeignKey(Tripulante.id))


class PqdEtapa:
    __tablename__ = 'pqd_etapa'
    __table_args__ = (
        CheckConstraint('qtd >= 0', name='ck_qtd'),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(
        ForeignKey(Etapa.id, ondelete='CASCADE')
    )
    tipo: Mapped[str] = mapped_column(String(5))  # VTC, LV, PREC, LIVRE
    qtd: Mapped[int] = mapped_column(SmallInteger())


class REVOEtapa:
    __tablename__ = 'revo_etapa'
    __table_args__ = (
        CheckConstraint('comb_transf >= 0', name='ck_comb_transf'),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(
        ForeignKey(Etapa.id, ondelete='CASCADE')
    )
    comb_transf: Mapped[int] = mapped_column(SmallInteger())


class HeavyCDS:
    __tablename__ = 'heavy_cds_etapa'
    __table_args__ = (
        CheckConstraint('dist >= 0', name='ck_heavy_cds_dist_nn'),
        CheckConstraint(
            'radial >= 0 AND radial < 360',
            name='ck_heavy_cds_radial_range',
        ),
        {'schema': 'estatistica'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    etapa_id: Mapped[int] = mapped_column(
        ForeignKey(Etapa.id, ondelete='CASCADE')
    )
    tipo: Mapped[str] = mapped_column(String(5))  # heavy, cds
    peso: Mapped[int] = mapped_column(SmallInteger())

    # ponto impacto
    dist: Mapped[int] = mapped_column(SmallInteger())
    radial: Mapped[int] = mapped_column(SmallInteger())
