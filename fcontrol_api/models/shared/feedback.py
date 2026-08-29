from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Feedback(Base):
    """Feedback/sugestão que o tripulante manda pelo portal FatBird.

    `uae` é a org ATIVA de quem enviou, congelada no envio: o feedback é
    tratado pela administração daquela unidade e não deve migrar se a
    pessoa for movimentada depois. É por essa coluna que o painel do
    client filtra — o gate `feedbacks.view` autoriza a ação, o escopo do
    alvo sai daqui.

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
    resposta: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # SET NULL: a resposta continua valendo mesmo que quem respondeu saia.
    respondido_por: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True,
        default=None,
    )
    respondido_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
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
    respondente = relationship(
        'User',
        lazy='selectin',
        foreign_keys=[respondido_por],
        init=False,
    )
