from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.models.shared.users import User

from .base import Base


class Proposta(Base):
    """Simulação de comissionamentos contra o teto de um exercício.

    Não é registro: nada aqui vira comissionamento sozinho. A hierarquia é
    Proposta → Cenários → Linhas, e a comparação acontece entre cenários da
    MESMA proposta (mesmo exercício, mesmo teto).
    """

    __tablename__ = 'propostas'
    __table_args__ = (
        CheckConstraint(
            'ano_ref >= 2026 AND ano_ref <= 2100',
            name='ck_propostas_ano_ref_plausivel',
        ),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    # Escopo multi-tenant: FK cross-Base usa o objeto-Column
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            Tenant.organizacao_id,
            ondelete='RESTRICT',
            onupdate='CASCADE',
        ),
    )
    nome: Mapped[str] = mapped_column(String(120))
    #: Exercício de referência — impõe o ano de abertura de toda linha.
    ano_ref: Mapped[int]
    #: Só 'rascunho' hoje; aprovação/promoção é fase posterior.
    status: Mapped[str] = mapped_column(
        String(20), server_default='rascunho', default='rascunho'
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    #: Ordena a lista e alimenta o "atualizado em" da tela. Tocado também
    #: quando só os cenários mudam — quem edita não distingue os dois.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cenarios: Mapped[list['Cenario']] = relationship(
        back_populates='proposta',
        cascade='all, delete-orphan',
        order_by='Cenario.ordem',
        default_factory=list,
    )


class Cenario(Base):
    """Uma alternativa de composição dentro da proposta.

    O código exibido (A, B, C…) NÃO é persistido: vem da posição, e por isso
    `ordem` é dado, não enfeite — renumerar aqui renomeia os cenários na tela.
    """

    __tablename__ = 'cenarios'
    __table_args__ = (
        # DEFERRED de propósito: o unit of work do SQLAlchemy emite
        # INSERT/UPDATE antes de DELETE dentro do mesmo mapper, então remover
        # um cenário do meio (o que renumera `ordem` dos seguintes) colidiria
        # com a unicidade no meio da transação, antes de a linha antiga sair.
        UniqueConstraint(
            'proposta_id',
            'ordem',
            name='uq_cenarios_proposta_ordem',
            deferrable=True,
            initially='DEFERRED',
        ),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    # `init=False`: quem preenche é o relationship no flush. Exigi-la no
    # construtor obrigaria a persistir a proposta antes de montar os cenários.
    proposta_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.propostas.id', ondelete='CASCADE'), init=False
    )
    nome: Mapped[str] = mapped_column(String(60))
    #: Id da paleta da UI (`sky`, `violet`…), nunca uma classe css.
    cor: Mapped[str] = mapped_column(String(20))
    ordem: Mapped[int]

    proposta: Mapped[Proposta] = relationship(
        back_populates='cenarios', init=False
    )
    linhas: Mapped[list['CenarioLinha']] = relationship(
        back_populates='cenario',
        cascade='all, delete-orphan',
        order_by='CenarioLinha.id',
        default_factory=list,
    )


class CenarioLinha(Base):
    """Um militar dentro de um cenário, com as duas pernas da ajuda de custo.

    Planeja por ANO, não por data: dia e mês não entram em cálculo nenhum —
    o impacto fiscal só olha o exercício — e a data cheia só é decidida
    quando a proposta virar comissionamento de verdade.
    """

    __tablename__ = 'cenario_linhas'
    __table_args__ = (
        # DEFERRED pelo mesmo motivo do `uq_cenarios_proposta_ordem`: tirar um
        # militar do cenário e recolocá-lo (é um toggle) insere a linha nova
        # antes de a antiga ser apagada.
        UniqueConstraint(
            'cenario_id',
            'user_id',
            name='uq_cenario_linhas_cenario_user',
            deferrable=True,
            initially='DEFERRED',
        ),
        CheckConstraint(
            'ano_fc >= ano_ab', name='ck_cenario_linhas_ordem_exercicios'
        ),
        CheckConstraint(
            'qtd_ab > 0 AND qtd_ab <= 2 AND qtd_fc > 0 AND qtd_fc <= 2',
            name='ck_cenario_linhas_qtd_ajuda',
        ),
        CheckConstraint(
            'base_ab >= 0 AND base_fc >= 0',
            name='ck_cenario_linhas_base_nao_negativa',
        ),
        {'schema': 'cegep'},
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    cenario_id: Mapped[int] = mapped_column(
        ForeignKey('cegep.cenarios.id', ondelete='CASCADE'), init=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id))

    base_ab: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    qtd_ab: Mapped[float]
    ano_ab: Mapped[int]

    base_fc: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    qtd_fc: Mapped[float]
    ano_fc: Mapped[int]

    cenario: Mapped[Cenario] = relationship(
        back_populates='linhas', init=False
    )
    #: Denormalizado só para LEITURA. O payload de escrita manda `user_id`;
    #: sem este join a tela perde o nome de todos os militares ao salvar.
    user: Mapped[User] = relationship(lazy='selectin', init=False)
