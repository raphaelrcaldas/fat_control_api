from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, registry, relationship

from fcontrol_api.schemas.quads import QuadType
from fcontrol_api.schemas.tripulantes import FuncList, OperList

table_registry = registry()


@table_registry.mapped_as_dataclass
class User:
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    pg: Mapped[str]
    nome_guerra: Mapped[str]
    nome_completo: Mapped[str] = mapped_column(nullable=True)
    ult_promo: Mapped[datetime] = mapped_column(nullable=True)
    id_fab: Mapped[int] = mapped_column(nullable=True, unique=True)
    saram: Mapped[int] = mapped_column(nullable=False, unique=True)
    unidade: Mapped[str] = mapped_column(nullable=False)
    cpf: Mapped[str] = mapped_column(nullable=True)
    nasc: Mapped[datetime] = mapped_column(nullable=True)
    celular: Mapped[str] = mapped_column(nullable=True)
    email_pess: Mapped[str] = mapped_column(nullable=True)
    email_fab: Mapped[str] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=True, init=False, onupdate=func.now()
    )


@table_registry.mapped_as_dataclass
class Tripulante:
    __tablename__ = 'tripulantes'

    id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    trig: Mapped[str] = mapped_column(String(3), unique=True)
    func: Mapped[FuncList]
    oper: Mapped[OperList]
    active: Mapped[bool]
    # user = relationship('User', backref='tripulante', uselist=False)
    user: Mapped[User] = relationship(lazy='joined', innerjoin=True)


@table_registry.mapped_as_dataclass
class Quad:
    __tablename__ = 'quad'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    description: Mapped[str]
    type: Mapped[QuadType]
    value: Mapped[int]

    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))
    trip = relationship('Tripulante', backref='quad', uselist=False)

    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=True, init=False, onupdate=func.now()
    )
