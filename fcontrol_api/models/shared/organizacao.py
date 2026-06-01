from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Organizacao(Base):
    __tablename__ = 'organizacoes'

    # PK = sigla canonica (codigo em uso: '11gt', 'glog', ...). E a mesma
    # chave string usada pelo control-plane (active_org) e pelo data-plane.
    sigla: Mapped[str] = mapped_column(String(20), primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    # Siglas alternativas (ex: esquadrao '1gt1', forma longa). Opcionais:
    # nem toda org tem todas; o admin preenche pela UI.
    sigla_2: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, default=None
    )
    sigla_3: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, default=None
    )
    alias: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    brasao_path: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )


class OrganizacaoRelacao(Base):
    """Vinculo hierarquico (pai -> filho) entre organizacoes.

    Tabela associativa M:N: uma organizacao filha pode ter mais de um pai.
    O vinculo e generico (sem tipo) - o pai controla tanto tarefas
    financeiras quanto operacionais do filho.
    """

    __tablename__ = 'organizacao_relacoes'
    __table_args__ = (
        CheckConstraint(
            'parent_id <> child_id',
            name='ck_organizacao_relacoes_sem_autoreferencia',
        ),
    )

    parent_id: Mapped[str] = mapped_column(
        ForeignKey('organizacoes.sigla', ondelete='CASCADE'),
        primary_key=True,
    )
    child_id: Mapped[str] = mapped_column(
        ForeignKey('organizacoes.sigla', ondelete='CASCADE'),
        primary_key=True,
    )
