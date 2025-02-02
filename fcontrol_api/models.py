from datetime import date, datetime

from sqlalchemy import ARRAY, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, registry, relationship

table_registry = registry()


@table_registry.mapped_as_dataclass
class PostoGrad:
    __tablename__ = 'posto_grad'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    ant: Mapped[int] = mapped_column(nullable=False)
    short: Mapped[str] = mapped_column(nullable=False)
    mid: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    soldo: Mapped[float] = mapped_column(nullable=False)
    circulo: Mapped[str] = mapped_column(nullable=False)


@table_registry.mapped_as_dataclass
class User:
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    p_g: Mapped[int] = mapped_column(ForeignKey('posto_grad.id'))
    esp: Mapped[str] = mapped_column(nullable=True)
    nome_guerra: Mapped[str]
    nome_completo: Mapped[str] = mapped_column(nullable=True)
    id_fab: Mapped[int] = mapped_column(nullable=True, unique=True)
    saram: Mapped[int] = mapped_column(nullable=False, unique=True)
    unidade: Mapped[str] = mapped_column(nullable=False)
    cpf: Mapped[str] = mapped_column(nullable=True)
    email_fab: Mapped[str] = mapped_column(nullable=True)
    email_pess: Mapped[str] = mapped_column(nullable=True)
    nasc: Mapped[date] = mapped_column(nullable=True)
    ult_promo: Mapped[date] = mapped_column(nullable=True)
    password: Mapped[str]
    ant_rel: Mapped[int] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )
    posto = relationship(
        'PostoGrad', backref='users', lazy='selectin', uselist=False
    )


@table_registry.mapped_as_dataclass
class Tripulante:
    __tablename__ = 'tripulantes'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    trig: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool]
    uae: Mapped[str]
    user = relationship(
        'User', backref='tripulantes', lazy='selectin', uselist=False
    )
    funcs = relationship(
        'Funcao', backref='tripulantes', lazy='selectin', uselist=True
    )


@table_registry.mapped_as_dataclass
class Funcao:
    __tablename__ = 'trip_funcs'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))
    func: Mapped[str]
    oper: Mapped[str]
    proj: Mapped[str]
    data_op: Mapped[date] = mapped_column(nullable=True)


@table_registry.mapped_as_dataclass
class Quad:
    __tablename__ = 'quad'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    description: Mapped[str] = mapped_column(nullable=True)
    type_id: Mapped[int] = mapped_column(ForeignKey('quads_type.id'))
    value: Mapped[date] = mapped_column(nullable=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))

    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )


@table_registry.mapped_as_dataclass
class Indisp:
    __tablename__ = 'indisps'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    date_start: Mapped[date]
    date_end: Mapped[date]
    mtv: Mapped[str] = mapped_column(nullable=False)
    obs: Mapped[str] = mapped_column(nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )
    user_created = relationship(
        'User',
        backref='indisps',
        lazy='selectin',
        uselist=False,
        foreign_keys=[created_by],
    )


@table_registry.mapped_as_dataclass
class QuadsGroup:
    __tablename__ = 'quads_group'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    short: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    uae: Mapped[str]
    types = relationship(
        'QuadsType', backref='quads_group', lazy='selectin', uselist=True
    )


@table_registry.mapped_as_dataclass
class QuadsType:
    __tablename__ = 'quads_type'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    group_id: Mapped[int] = mapped_column(ForeignKey('quads_group.id'))
    short: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    exclude: Mapped[ARRAY] = mapped_column(ARRAY(String), nullable=False)
