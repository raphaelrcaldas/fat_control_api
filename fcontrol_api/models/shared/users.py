from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.models.shared.posto_grad import PostoGrad

from .base import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    p_g: Mapped[PostoGradEnum] = mapped_column(
        String(2), ForeignKey(PostoGrad.short)
    )
    quadro: Mapped[str] = mapped_column(nullable=True)
    esp: Mapped[str] = mapped_column(nullable=True)
    nome_guerra: Mapped[str]
    nome_completo: Mapped[str] = mapped_column(nullable=True)
    id_fab: Mapped[str] = mapped_column(String(6), nullable=True, unique=True)
    saram: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)
    unidade: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            'organizacoes.sigla', ondelete='RESTRICT', onupdate='CASCADE'
        ),
        nullable=False,
    )
    cpf: Mapped[str] = mapped_column(String(11), nullable=True)
    telefone: Mapped[str] = mapped_column(String(11), nullable=True)
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
    promocoes = relationship(
        'UserPromo',
        init=False,
        lazy='selectin',
        order_by='UserPromo.data_promo.desc()',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )


class UserPromo(Base):
    __tablename__ = 'promo_users'
    __table_args__ = (
        UniqueConstraint('user_id', 'p_g', name='uq_promo_users_user_pg'),
        UniqueConstraint(
            'user_id', 'data_promo', name='uq_promo_users_user_data'
        ),
    )

    id: Mapped[int] = mapped_column(
        Identity(), init=False, primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id, ondelete='CASCADE')
    )
    p_g: Mapped[PostoGradEnum] = mapped_column(
        String(2), ForeignKey(PostoGrad.short)
    )
    data_promo: Mapped[date] = mapped_column(nullable=False)

    posto = relationship('PostoGrad', lazy='joined', uselist=False)
