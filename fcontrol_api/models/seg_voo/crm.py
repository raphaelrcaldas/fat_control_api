from datetime import date

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.users import User

from .base import Base


class CrmCertificado(Base):
    __tablename__ = 'crm_certificados'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), unique=True)
    data_realizacao: Mapped[date | None]
    data_validade: Mapped[date | None]

    user = relationship(
        User,
        backref='crm_certificado',
        lazy='selectin',
        uselist=False,
    )
