from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Feedback(Base):
    """Feedback/sugestão que o tripulante manda pelo portal FatBird.

    `uae` é a org ATIVA de quem enviou, congelada no envio: diz só de qual
    unidade o feedback saiu e não deve migrar se a pessoa for movimentada
    depois. O tratamento é control-plane de SISTEMA, cross-tenant — o
    painel do client (`routers/admin/feedbacks.py`) não filtra por `uae`;
    a conversa vive em `FeedbackEvento`.

    `tipo` e `status` são String no banco (não ENUM nativo): a lista
    fechada mora nos enums Python e é validada pelo schema Pydantic —
    mesmo contrato de `tenants.tema`. Valor novo não pede migration.
    """

    __tablename__ = 'feedbacks'

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    # CASCADE: feedback é dado do usuário; some com ele.
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE')
    )
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            'organizacoes.sigla', ondelete='RESTRICT', onupdate='CASCADE'
        ),
    )
    tipo: Mapped[str] = mapped_column(String(20))
    titulo: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str] = mapped_column(Text)
    # Rota do front de onde o feedback foi aberto (ex.: '/ops/sebo').
    # Nulo quando enviado pela própria página de feedback.
    rota: Mapped[str | None] = mapped_column(
        String(120), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(20), default='aberto')
    # Derivada do `app_client` do token no envio, nunca escolhida pelo
    # front: separa a caixa por app (ver `routers/feedbacks.py`) e diz à
    # administração de onde veio.
    origem: Mapped[str] = mapped_column(
        String(20), server_default='fatbird', default='fatbird'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=None,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    autor = relationship(
        'User',
        lazy='selectin',
        foreign_keys=[user_id],
        init=False,
    )


class FeedbackEvento(Base):
    """Um item da conversa de um feedback: mensagem ou mudança de status.

    A `descricao` do feedback é a abertura da conversa e NÃO é copiada
    para cá. Mensagens são definitivas (sem edição nem exclusão): a
    correção se faz com outra mensagem.

    Ordem canônica: `created_at, id` — mensagem e status gravados na
    mesma ação empatam no instante, e o `id` preserva a ordem de inserção.
    """

    __tablename__ = 'feedback_eventos'
    __table_args__ = (
        CheckConstraint(
            "(tipo = 'mensagem' AND texto IS NOT NULL AND status IS NULL) "
            "OR (tipo = 'status' AND status IS NOT NULL AND texto IS NULL)",
            name='ck_feedback_eventos_tipo_conteudo',
        ),
        # A conversa é sempre lida por feedback, em ordem.
        Index('ix_feedback_eventos_feedback', 'feedback_id', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    # CASCADE: a conversa some com o feedback.
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey('feedbacks.id', ondelete='CASCADE', onupdate='CASCADE')
    )
    # SET NULL: o evento continua valendo se quem escreveu sair.
    autor_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True,
    )
    tipo: Mapped[str] = mapped_column(String(20))
    texto: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    autor = relationship(
        'User',
        lazy='selectin',
        foreign_keys=[autor_id],
        init=False,
    )
