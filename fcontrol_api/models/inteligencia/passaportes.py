from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.users import User

from .base import Base


class Passaporte(Base):
    __tablename__ = 'passaportes'
    __table_args__ = (
        CheckConstraint(
            'data_expedicao_passaporte IS NULL '
            'OR validade_passaporte IS NULL '
            'OR data_expedicao_passaporte <= validade_passaporte',
            name='ck_passaporte_expedicao_le_validade',
        ),
        CheckConstraint(
            'data_expedicao_visa IS NULL '
            'OR validade_visa IS NULL '
            'OR data_expedicao_visa <= validade_visa',
            name='ck_visa_expedicao_le_validade',
        ),
        {'schema': 'inteligencia'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), unique=True)
    passaporte: Mapped[str | None] = mapped_column(String(20))
    data_expedicao_passaporte: Mapped[date | None]
    validade_passaporte: Mapped[date | None]
    visa: Mapped[str | None] = mapped_column(String(20))
    data_expedicao_visa: Mapped[date | None]
    validade_visa: Mapped[date | None]

    user = relationship(
        User,
        backref='passaporte_registro',
        lazy='selectin',
        uselist=False,
    )
