from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Identity, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.users import User

from .base import Base


class DadosBancarios(Base):
    __tablename__ = 'dados_bancarios'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), unique=True)
    banco: Mapped[str]
    codigo_banco: Mapped[str]
    agencia: Mapped[str]
    conta: Mapped[str]

    remuneracao: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), default=None
    )
    mes_ano: Mapped[date | None] = mapped_column(default=None)

    aux_transp: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship(
        User, backref='dados_bancarios', lazy='selectin', uselist=False
    )
