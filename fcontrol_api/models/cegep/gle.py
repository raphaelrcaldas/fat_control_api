"""Missões de GLE: o trabalho salvo da calculadora.

Uma `MissaoGle` guarda os dados que o usuário informa para calcular a
Gratificação de Localidade Especial — os trechos de permanência e os
militares — para que o cálculo possa ser reaberto, conferido e corrigido.
O **valor não é gravado**: ele é recalculado a partir dos trechos, do soldo
vigente e da classificação da localidade, que são a fonte da verdade.

Contexto de domínio em `docs/dominio/gle.md`.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.estados_cidades import GrupoLocEsp
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.models.shared.users import User

from .base import Base


class MissaoGle(Base):
    """Um trabalho de apuração de GLE, escopado à organização.

    A `descricao` é o identificador que o usuário reconhece (a OS que
    originou a apuração). Não há unicidade: duas apurações podem descrever
    o mesmo documento sem que isso seja erro.
    """

    __tablename__ = 'missao_gle'
    # O dict de opções precisa ser o último item da tupla: sem ele, o
    # `__table_args__` da Base (`{'schema': 'cegep'}`) é sobrescrito e a
    # tabela nasce em `public`.
    __table_args__ = ({'schema': 'cegep'},)

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    descricao: Mapped[str] = mapped_column(nullable=False)
    obs: Mapped[str | None] = mapped_column(nullable=True, default=None)

    # Escopo multi-tenant: FK cross-Base usa o objeto-Column.
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            Tenant.organizacao_id,
            ondelete='RESTRICT',
            onupdate='CASCADE',
        ),
        init=False,
        default=None,
    )
    #: `func.now()`, nunca a string `'now()'`: como string o Postgres
    #: avalia uma vez no `CREATE TABLE` e congela o instante como
    #: constante — toda missão nasceria com a data da migration.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )

    trechos: Mapped[list['TrechoGle']] = relationship(
        'TrechoGle',
        back_populates='missao',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='TrechoGle.chegada',
        init=False,
        default_factory=list,
    )
    militares: Mapped[list['MilitarGle']] = relationship(
        'MilitarGle',
        back_populates='missao',
        cascade='all, delete-orphan',
        lazy='selectin',
        init=False,
        default_factory=list,
    )


class TrechoGle(Base):
    """Permanência numa localidade especial: onde, de quando até quando.

    A categoria (A/B) **não** é coluna: vem de `GrupoLocEsp.grupo`, para a
    missão acompanhar uma eventual reclassificação da localidade em vez de
    congelar um valor que o usuário digitou.
    """

    __tablename__ = 'trecho_gle'
    __table_args__ = (
        CheckConstraint('afastamento > chegada', name='ck_trecho_gle_periodo'),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    missao_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.missao_gle.id', ondelete='CASCADE'), init=False
    )
    loc_esp_id: Mapped[int] = mapped_column(
        ForeignKey(GrupoLocEsp.id, ondelete='RESTRICT')
    )
    chegada: Mapped[datetime] = mapped_column(nullable=False)
    afastamento: Mapped[datetime] = mapped_column(nullable=False)

    missao: Mapped[MissaoGle] = relationship(
        'MissaoGle', back_populates='trechos', init=False
    )


class MilitarGle(Base):
    """Militar que cumpriu a missão.

    `p_g` é **snapshot histórico**, não espelho do posto atual: promover
    alguém não pode reescrever o valor de uma apuração já feita. Mesma
    decisão de `om_tripulacao.p_g` — ver `docs/ai/notes/dominio.md`.

    A FK para `posto_grad.short` valida o valor, não o congela: o que
    preserva a apuração é ninguém reescrever esta coluna. É o mesmo
    arranjo de `om_tripulacao`, mantido por consistência.
    """

    __tablename__ = 'militar_gle'
    __table_args__ = (
        UniqueConstraint(
            'missao_id', 'user_id', name='uq_militar_gle_missao_user'
        ),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    missao_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.missao_gle.id', ondelete='CASCADE'), init=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id, ondelete='RESTRICT')
    )
    p_g: Mapped[str] = mapped_column(ForeignKey(PostoGrad.short))

    missao: Mapped[MissaoGle] = relationship(
        'MissaoGle', back_populates='militares', init=False
    )
    # Cross-Base (`shared`): passa a classe, não a string.
    user: Mapped[User] = relationship(User, init=False, lazy='selectin')
