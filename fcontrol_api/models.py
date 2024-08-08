from datetime import datetime
from enum import Enum

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, registry, relationship

table_registry = registry()


class QuadType(str, Enum):
    nacional = 'nacional'
    local = 'local'
    desloc = 'desloc'
    sobr = 'sobr'
    sar = 'sar'


class FuncList(str, Enum):
    mc = 'mc'
    lm = 'lm'
    tf = 'tf'
    os = 'os'
    oe = 'oe'


class OperList(str, Enum):
    AL = 'AL'  # ALUNO
    BA = 'BA'  # BASICO
    OP = 'OP'  # OPERACIONAL
    IN = 'IN'  # INSTRUTOR


@table_registry.mapped_as_dataclass
class User:
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    password: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )


@table_registry.mapped_as_dataclass
class Tripulante:
    __tablename__ = 'tripulantes'

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'), primary_key=True
    )
    trig: Mapped[str] = mapped_column(unique=True)
    func: Mapped[FuncList]
    oper: Mapped[OperList]
    active: Mapped[bool]
    user = relationship('User', backref='tripulante', uselist=False)


@table_registry.mapped_as_dataclass
class Quad:
    __tablename__ = 'quad'

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    # description: Mapped[str]
    type: Mapped[QuadType]
    value: Mapped[int]

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    # user_name = relationship('User', foreign_keys = user_id)
