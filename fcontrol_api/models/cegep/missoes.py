from datetime import date, datetime

from sqlalchemy import ForeignKey, Identity, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.users import User

from .base import Base


class FragEtiqueta(Base):
    """Tabela associativa para relação many-to-many entre FragMis e Etiqueta"""

    __tablename__ = 'frag_etiqueta'

    frag_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.frag_mis.id', ondelete='CASCADE'), primary_key=True
    )
    etiqueta_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.etiqueta.id', ondelete='CASCADE'), primary_key=True
    )


class Etiqueta(Base):
    """Modelo para etiquetas de missões"""

    __tablename__ = 'etiqueta'

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    cor: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # Hex color #RRGGBB
    descricao: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Relação many-to-many com FragMis (definida via back_populates no FragMis)
    missoes = relationship(
        'FragMis',
        secondary='cegep.frag_etiqueta',
        back_populates='etiquetas',
        init=False,
        default_factory=list,
    )


class FragMis(Base):
    __tablename__ = 'frag_mis'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    tipo_doc: Mapped[str] = mapped_column(nullable=False)
    n_doc: Mapped[int] = mapped_column(nullable=False)
    desc: Mapped[str] = mapped_column(nullable=False)
    tipo: Mapped[str] = mapped_column(nullable=False)
    afast: Mapped[datetime] = mapped_column(nullable=False)
    regres: Mapped[datetime] = mapped_column(nullable=False)
    acrec_desloc: Mapped[bool] = mapped_column(server_default='false')
    obs: Mapped[str] = mapped_column(nullable=True)
    indenizavel: Mapped[bool] = mapped_column(nullable=False)
    custos: Mapped[dict] = mapped_column(
        JSONB, server_default='{}', nullable=False, init=False
    )
    pernoites = relationship(
        'PernoiteFrag',
        backref='frag_mis',
        cascade='all, delete-orphan',
        lazy='selectin',
        uselist=True,
        order_by='PernoiteFrag.data_ini',
    )
    users = relationship(
        'UserFrag',
        backref='frag_mis',
        cascade='all, delete-orphan',
        lazy='noload',
        uselist=True,
    )
    etiquetas = relationship(
        'Etiqueta',
        secondary='cegep.frag_etiqueta',
        back_populates='missoes',
        lazy='selectin',
        init=False,
        default_factory=list,
    )


class PernoiteFrag(Base):
    __tablename__ = 'pernoite_frag'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    cidade_id: Mapped[int] = mapped_column(ForeignKey(Cidade.codigo))
    frag_id: Mapped[int] = mapped_column(ForeignKey(FragMis.id))
    acrec_desloc: Mapped[bool]
    data_ini: Mapped[date]
    data_fim: Mapped[date]
    obs: Mapped[str] = mapped_column(nullable=True)
    meia_diaria: Mapped[bool]
    cidade: Cidade = relationship(
        Cidade, init=False, backref='frag_mis', lazy='selectin', uselist=False
    )


class UserFrag(Base):
    __tablename__ = 'users_frag'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    frag_id: Mapped[int] = mapped_column(ForeignKey(FragMis.id))
    sit: Mapped[str] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    p_g: Mapped[int] = mapped_column(ForeignKey(PostoGrad.short))
    posto: PostoGrad = relationship(
        PostoGrad,
        init=False,
        backref='users_frag',
        lazy='selectin',
        uselist=False,
    )
    user: User = relationship(
        User, init=False, backref='users_frag', lazy='selectin', uselist=False
    )
