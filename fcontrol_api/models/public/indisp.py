from datetime import date, datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Identity, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Indisp(Base):
    __tablename__ = 'indisps'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    date_start: Mapped[date]
    date_end: Mapped[date]
    mtv: Mapped[str] = mapped_column(nullable=False)
    obs: Mapped[str] = mapped_column(nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        init=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
    )
    user_created = relationship(
        'User',
        backref='indisps',
        lazy='selectin',
        foreign_keys=[created_by],
    )
