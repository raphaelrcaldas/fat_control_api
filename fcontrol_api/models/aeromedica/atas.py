from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.shared.users import User

from .base import Base


class AtaInspecao(Base):
    __tablename__ = 'atas_inspecao'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    file_path: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int]
    letra_finalidade: Mapped[str | None] = mapped_column(
        String(1), default=None
    )
    data_realizacao: Mapped[date | None] = mapped_column(default=None)
    validade_inspsau: Mapped[date | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )
