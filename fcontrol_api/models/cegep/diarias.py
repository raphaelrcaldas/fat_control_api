from datetime import date

from sqlalchemy import ForeignKey, Identity
from sqlalchemy.orm import Mapped, mapped_column

from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.models.public.posto_grad import PostoGrad

from .base import Base


class GrupoCidade(Base):
    __tablename__ = 'grupos_cidade'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    grupo: Mapped[int] = mapped_column(nullable=False)
    cidade_id: Mapped[int] = mapped_column(ForeignKey(Cidade.codigo))


class GrupoPg(Base):
    __tablename__ = 'grupos_pg'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    grupo: Mapped[int] = mapped_column(nullable=False)
    pg_short: Mapped[int] = mapped_column(ForeignKey(PostoGrad.short))


class DiariaValor(Base):
    __tablename__ = 'valor_diarias'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    grupo_pg: Mapped[int]
    grupo_cid: Mapped[int]
    valor: Mapped[float] = mapped_column(nullable=False)
    data_inicio: Mapped[date] = mapped_column(nullable=False)
    data_fim: Mapped[date] = mapped_column(nullable=True)
