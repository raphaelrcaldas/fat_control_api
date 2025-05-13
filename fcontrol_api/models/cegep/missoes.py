from datetime import datetime

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.users import User

from .base import Base


class FragMis(Base):
    __tablename__ = 'frag_mis'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    obs: Mapped[str] = mapped_column(nullable=True)


class PernoiteFrag(Base):
    __tablename__ = 'pernoite_frag'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    cidade_id: Mapped[int] = mapped_column(ForeignKey(Cidade.codigo))
    acrec_desloc: Mapped[bool] = mapped_column(nullable=False)
    data_ini: Mapped[datetime] = mapped_column(nullable=True)
    data_fim: Mapped[datetime] = mapped_column(nullable=True)
    obs: Mapped[str] = mapped_column(nullable=True)


class UserFrag(Base):
    __tablename__ = 'users_frag'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    frag_id: Mapped[int] = mapped_column(ForeignKey(FragMis.id))
    sit: Mapped[str] = mapped_column(nullable=False)
    # commis_id: Mapped[int] = mapped_column(nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))
    p_g: Mapped[int] = mapped_column(ForeignKey(PostoGrad.short))
