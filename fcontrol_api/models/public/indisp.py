from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Indisp(Base):
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
        foreign_keys=[created_by],
    )
