from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, unique=True, nullable=False
    )
    p_g: Mapped[int] = mapped_column(ForeignKey('posto_grad.id'))
    esp: Mapped[str] = mapped_column(nullable=True)
    nome_guerra: Mapped[str]
    nome_completo: Mapped[str] = mapped_column(nullable=True)
    id_fab: Mapped[int] = mapped_column(nullable=True, unique=True)
    saram: Mapped[int] = mapped_column(nullable=False, unique=True)
    unidade: Mapped[str] = mapped_column(nullable=False)
    cpf: Mapped[str] = mapped_column(nullable=True)
    email_fab: Mapped[str] = mapped_column(nullable=True)
    email_pess: Mapped[str] = mapped_column(nullable=True)
    nasc: Mapped[date] = mapped_column(nullable=True)
    ult_promo: Mapped[date] = mapped_column(nullable=True)
    password: Mapped[str]
    ant_rel: Mapped[int] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )
    posto = relationship(
        'PostoGrad', backref='users', lazy='selectin', uselist=False
    )
