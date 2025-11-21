from datetime import datetime

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.users import User

from .base import Base


class DadosBancarios(Base):
    __tablename__ = 'dados_bancarios'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), unique=True)
    banco: Mapped[str]
    codigo_banco: Mapped[str]
    agencia: Mapped[str]
    conta: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        init=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        init=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship(
        User, backref='dados_bancarios', lazy='selectin', uselist=False
    )
