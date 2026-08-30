from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Predicado do índice parcial de dedupe de tarefas abertas. Vive numa
# constante porque o `on_conflict_do_nothing` do serviço precisa citar um
# `index_where` TEXTUALMENTE equivalente ao do índice — se os dois textos
# divergirem, o Postgres não casa o índice e o INSERT quebra em runtime.
TAREFA_ABERTA_WHERE = "escopo = 'tarefa' AND resolved_at IS NULL"


class Notificacao(Base):
    """Notificação in-app (client + FatBird), numa tabela só.

    `escopo` discrimina os dois modos: `'direta'` (endereçada a um
    `user_id`, ciclo de leitura via `read_at`) e `'tarefa'` (endereçada a
    uma permissão `req_resource`+`req_action`, ciclo via `resolved_at`).
    Tarefa é endereçada por PERMISSÃO — não por role literal — porque o
    admin tem bypass sem linhas em `role_permissions`; o destinatário é
    resolvido na LEITURA (`services/notificacoes.condicoes_visiveis`), o
    que acompanha mudanças de RBAC sem reprocessar nada. As colunas de
    tarefa já nascem no schema para evitar migration futura, mas nada as
    emite na v1.

    `audiencia` segrega por app (`'tripulante'` → só FatBird, `'gestor'`
    → só client) e é imposta no backend pelo `app_client` do token.

    `escopo`/`audiencia`/`tipo` são String no banco (não ENUM nativo): a
    lista fechada mora em `enums/notificacao.py` — valor novo não pede
    migration, mesmo contrato de `feedbacks.tipo`.

    `payload` guarda dados para rótulo e deep-link (contagens, nomes) —
    NUNCA rota (os dois fronts têm URLs diferentes; cada um monta a sua a
    partir de `tipo`/`recurso_id`) e NUNCA PII de terceiros.
    """

    __tablename__ = 'notificacoes'
    __table_args__ = (
        # Cada escopo exige o seu endereçamento e proíbe o do outro — de
        # quebra, restringe `escopo` aos dois valores válidos.
        CheckConstraint(
            "(escopo = 'direta' AND user_id IS NOT NULL "
            'AND req_resource IS NULL) '
            "OR (escopo = 'tarefa' AND user_id IS NULL "
            'AND req_resource IS NOT NULL)',
            name='ck_notificacoes_escopo_enderecamento',
        ),
        # Tarefa por permissão só faz sentido no client: tripulante não
        # tem role, então nunca resolveria `req_resource`+`req_action`.
        CheckConstraint(
            "escopo != 'tarefa' OR audiencia = 'gestor'",
            name='ck_notificacoes_tarefa_gestor',
        ),
        # Dedupe de tarefas ABERTAS: reemitir a mesma tarefa vira no-op
        # (`on_conflict_do_nothing` no serviço); resolvida sai do índice e
        # a próxima ocorrência pode abrir de novo.
        Index(
            'uq_notificacoes_tarefa_aberta',
            'uae',
            'tipo',
            'chave_dedupe',
            unique=True,
            postgresql_where=text(TAREFA_ABERTA_WHERE),
        ),
        # Inbox do usuário (lista e contador de não lidas).
        Index('ix_notificacoes_inbox', 'user_id', 'read_at'),
        # Tarefas pendentes por org (lista e contador do client).
        Index('ix_notificacoes_tarefas', 'uae', 'escopo', 'resolved_at'),
    )

    id: Mapped[int] = mapped_column(Identity(), init=False, primary_key=True)
    # Org de origem do evento, congelada na emissão. Diretas a exibem no
    # item (a pessoa pode ter lotação em mais de uma unidade); tarefas são
    # filtradas por ela contra a org ativa do token.
    uae: Mapped[str] = mapped_column(
        String(20),
        ForeignKey(
            'organizacoes.sigla', ondelete='RESTRICT', onupdate='CASCADE'
        ),
    )
    escopo: Mapped[str] = mapped_column(String(12))
    audiencia: Mapped[str] = mapped_column(String(12))
    tipo: Mapped[str] = mapped_column(String(50))
    titulo: Mapped[str] = mapped_column(String(140))
    # Recurso de domínio que originou a notificação (ex.: 'ops.quadro') —
    # namespace próprio, junto de `recurso_id` serve ao deep-link do front.
    recurso: Mapped[str] = mapped_column(String(60))
    descricao: Mapped[str | None] = mapped_column(
        String(300), nullable=True, default=None
    )
    recurso_id: Mapped[int | None] = mapped_column(nullable=True, default=None)

    # ── Modo direta ────────────────────────────────────────────────
    # CASCADE: a notificação é dado do destinatário; some com ele.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'),
        nullable=True,
        default=None,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # ── Modo tarefa (dormente na v1: nada emite) ───────────────────
    req_resource: Mapped[str | None] = mapped_column(
        String(120), nullable=True, default=None
    )
    req_action: Mapped[str | None] = mapped_column(
        String(40), nullable=True, default=None
    )
    chave_dedupe: Mapped[str | None] = mapped_column(
        String(120), nullable=True, default=None
    )
    # SET NULL: o histórico de resolução vale mesmo que quem resolveu saia.
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True,
        default=None,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default='{}', default_factory=dict
    )
    # SET NULL: a notificação continua valendo mesmo que o emissor saia.
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
