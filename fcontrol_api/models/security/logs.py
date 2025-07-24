from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..public.users import User
from .base import Base


class UserActionLog(Base):
    __tablename__ = 'user_action_logs'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), nullable=False)
    action: Mapped[str] = mapped_column(nullable=False)
    resource: Mapped[str] = mapped_column(nullable=False)
    resource_id: Mapped[int | None] = mapped_column(nullable=True)
    before: Mapped[str | None]
    after: Mapped[str | None]
    timestamp: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )

    user = relationship(User, lazy='selectin')
