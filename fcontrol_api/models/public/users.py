from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.enums.posto_grad import PostoGradEnum

from .base import Base
from .posto_grad import PostoGrad


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    p_g: Mapped[PostoGradEnum] = mapped_column(
        String(2), ForeignKey(PostoGrad.short)
    )
    esp: Mapped[str] = mapped_column(nullable=True)
    nome_guerra: Mapped[str]
    nome_completo: Mapped[str] = mapped_column(nullable=True)
    id_fab: Mapped[str] = mapped_column(String(6), nullable=True, unique=True)
    saram: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)
    unidade: Mapped[str] = mapped_column(String(8), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), nullable=True)
    email_fab: Mapped[str] = mapped_column(nullable=True)
    email_pess: Mapped[str] = mapped_column(nullable=True)
    nasc: Mapped[date] = mapped_column(nullable=True)
    ult_promo: Mapped[date] = mapped_column(nullable=True)
    password: Mapped[str]
    ant_rel: Mapped[int] = mapped_column(nullable=True)
    first_login: Mapped[bool] = mapped_column(default=True)
    active: Mapped[bool] = mapped_column(init=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )
    posto = relationship(
        'PostoGrad', backref='users', lazy='selectin', uselist=False
    )
