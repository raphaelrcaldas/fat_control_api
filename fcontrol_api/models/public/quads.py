from datetime import date, datetime

from sqlalchemy import ARRAY, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .. import Base


class Quad(Base):
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


class QuadsGroup(Base):
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


class QuadsType(Base):
    __tablename__ = 'quads_type'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    group_id: Mapped[int] = mapped_column(ForeignKey('quads_group.id'))
    short: Mapped[str] = mapped_column(nullable=False)
    long: Mapped[str] = mapped_column(nullable=False)
    exclude: Mapped[ARRAY] = mapped_column(ARRAY(String), nullable=False)
