from datetime import date, datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, registry, relationship

table_registry = registry()


@table_registry.mapped_as_dataclass
class User:
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    p_g: Mapped[str]
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
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )


@table_registry.mapped_as_dataclass
class Tripulante:
    __tablename__ = 'tripulantes'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    trig: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool]
    uae: Mapped[str]
    user = relationship('User', backref='tripulantes', uselist=False)
    funcs = relationship('Funcao', backref='tripulantes', uselist=True)


@table_registry.mapped_as_dataclass
class Funcao:
    __tablename__ = 'trip_funcs'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))
    func: Mapped[str]
    oper: Mapped[str]
    proj: Mapped[str]
    data_op: Mapped[date] = mapped_column(nullable=True)


@table_registry.mapped_as_dataclass
class Quad:
    __tablename__ = 'quad'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    description: Mapped[str]
    type: Mapped[str]
    value: Mapped[int]
    trip_id: Mapped[int] = mapped_column(ForeignKey('tripulantes.id'))

    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=True, init=False, onupdate=func.now()
    )
