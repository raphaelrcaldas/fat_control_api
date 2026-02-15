from datetime import date, datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Aeronave(Base):
    __tablename__ = 'aeronaves'

    matricula: Mapped[str] = mapped_column(
        String(4), primary_key=True
    )
    active: Mapped[bool]
    sit: Mapped[str] = mapped_column(String(2))
    obs: Mapped[str | None]
    prox_insp: Mapped[date | None]
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
        onupdate=lambda: datetime.now(timezone.utc),
    )
