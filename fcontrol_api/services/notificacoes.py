"""Emissão e visibilidade de notificações in-app.

Contrato de emissão — o MESMO de `services/logs.py:log_user_action`:
`session.add` SEM commit. O call site comita a notificação junto da
mutação que a originou; se a mutação der rollback, a notificação vai
junto (nunca notifica um evento que não aconteceu).
"""

from datetime import datetime, timezone

from sqlalchemy import ColumnElement, and_, or_, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.enums.notificacao import NotifAudiencia, NotifEscopo
from fcontrol_api.models.shared.notificacao import (
    TAREFA_ABERTA_WHERE,
    Notificacao,
)
from fcontrol_api.models.shared.users import User
from fcontrol_api.services.auth import FATBIRD_CLIENT, get_user_roles


def audiencia_do_app(app_client: str | None) -> str:
    """Deriva a audiência do `app_client` do TOKEN, nunca do request.

    É a segregação por app imposta no backend: o front não escolhe o que
    vê — token do FatBird só enxerga notificações de tripulante, token do
    client só as de gestor, mesmo quando é a mesma pessoa nos dois papéis
    (os deep-links de um app não existem no outro).
    """
    if app_client == FATBIRD_CLIENT:
        return NotifAudiencia.TRIPULANTE.value
    return NotifAudiencia.GESTOR.value


async def condicoes_visiveis(
    session: AsyncSession,
    user: User,
    active_org: str | None,
    app_client: str | None,
) -> ColumnElement[bool]:
    """Predicado de visibilidade, reusado por lista e contador.

    Diretas ignoram a org ativa (dado da pessoa — o item exibe a sigla);
    tarefas filtram por `uae == active_org`.

    Tarefa é endereçada por permissão e o destinatário é resolvido AQUI,
    na leitura: admin da org vê todas as tarefas dela (bypass — ele não
    tem linhas em `role_permissions`, então filtrar por grant o excluiria);
    não-admin vê as tarefas cujo `req_resource`+`req_action` ele possui.
    Resolver na leitura também acompanha mudanças de RBAC sem reprocessar
    notificações já emitidas.

    Os dois ramos filtram `audiencia` explicitamente. Hoje isso é
    redundante (tarefa é sempre `gestor` pelo CheckConstraint, e o
    tripulante já saiu no early-return acima), mas deixa a amarra de app
    local a cada query em vez de depender de duas invariantes distantes.
    """
    aud = audiencia_do_app(app_client)
    direta = and_(
        Notificacao.escopo == NotifEscopo.DIRETA.value,
        Notificacao.user_id == user.id,
        Notificacao.audiencia == aud,
    )

    # FatBird nunca vê tarefa (tripulante não tem role); sem org ativa
    # (contexto Sistema) não há lente de unidade para as tarefas.
    if aud == NotifAudiencia.TRIPULANTE.value or active_org is None:
        return direta

    roles = await get_user_roles(user.id, session, active_org)
    if roles.get('role') == 'admin':
        tarefa = and_(
            Notificacao.escopo == NotifEscopo.TAREFA.value,
            Notificacao.audiencia == aud,
            Notificacao.uae == active_org,
        )
    else:
        pares = [(p['resource'], p['name']) for p in roles.get('perms', [])]
        # Sem nenhuma permissão não há tarefa visível — e retornar direto
        # evita `tuple_().in_([])`, que emite SQL degenerado.
        if not pares:
            return direta
        tarefa = and_(
            Notificacao.escopo == NotifEscopo.TAREFA.value,
            Notificacao.audiencia == aud,
            Notificacao.uae == active_org,
            tuple_(Notificacao.req_resource, Notificacao.req_action).in_(
                pares
            ),
        )

    return or_(direta, tarefa)


async def notificar_usuarios(
    session: AsyncSession,
    *,
    user_ids: list[int],
    uae: str,
    audiencia: str,
    tipo: str,
    titulo: str,
    recurso: str,
    recurso_id: int | None = None,
    descricao: str | None = None,
    payload: dict | None = None,
    created_by: int | None = None,
) -> list[Notificacao]:
    """Emite notificações DIRETAS (uma por destinatário), sem commit.

    `audiencia` é obrigatória e explícita no call site: só quem emite
    sabe em qual app o evento faz sentido (quadrinho é do portal;
    tarefa de gestão é do client) — um default esconderia essa decisão.

    Quem originou o evento não é notificado dele (`created_by` sai do
    alvo): "você recebeu" não faz sentido para quem acabou de fazer.
    """
    notificacoes = [
        Notificacao(
            uae=uae,
            escopo=NotifEscopo.DIRETA.value,
            audiencia=audiencia,
            tipo=tipo,
            titulo=titulo,
            recurso=recurso,
            recurso_id=recurso_id,
            descricao=descricao,
            user_id=user_id,
            payload=payload or {},
            created_by=created_by,
        )
        for user_id in dict.fromkeys(user_ids)
        if user_id != created_by
    ]
    session.add_all(notificacoes)
    return notificacoes


async def abrir_tarefa(
    session: AsyncSession,
    *,
    uae: str,
    tipo: str,
    titulo: str,
    req_resource: str,
    req_action: str,
    chave_dedupe: str,
    recurso: str,
    recurso_id: int | None = None,
    descricao: str | None = None,
    payload: dict | None = None,
    created_by: int | None = None,
) -> None:
    """Abre uma tarefa compartilhada (sem call site na v1), sem commit.

    Dedupe pelo índice parcial `uq_notificacoes_tarefa_aberta`: enquanto
    houver tarefa ABERTA com a mesma (uae, tipo, chave_dedupe), reemitir
    é no-op — o `index_where` cita o MESMO texto do índice
    (`TAREFA_ABERTA_WHERE`), senão o Postgres não casa o índice parcial.
    """
    stmt = (
        insert(Notificacao)
        .values(
            uae=uae,
            escopo=NotifEscopo.TAREFA.value,
            # Constraint do model: tarefa é sempre de gestor (tripulante
            # não tem role para resolvê-la).
            audiencia=NotifAudiencia.GESTOR.value,
            tipo=tipo,
            titulo=titulo,
            recurso=recurso,
            recurso_id=recurso_id,
            descricao=descricao,
            req_resource=req_resource,
            req_action=req_action,
            chave_dedupe=chave_dedupe,
            payload=payload or {},
            created_by=created_by,
        )
        .on_conflict_do_nothing(
            index_elements=['uae', 'tipo', 'chave_dedupe'],
            index_where=text(TAREFA_ABERTA_WHERE),
        )
    )
    await session.execute(stmt)


async def resolver_tarefas(
    session: AsyncSession,
    *,
    uae: str,
    tipo: str,
    chave_dedupe: str,
    resolved_by: int | None = None,
) -> int:
    """Resolve as tarefas ABERTAS que casam a chave, sem commit.

    O `WHERE resolved_at IS NULL` torna a operação idempotente e preserva
    o histórico de resoluções anteriores (não sobrescreve quem resolveu).
    """
    result = await session.execute(
        update(Notificacao)
        .where(
            Notificacao.escopo == NotifEscopo.TAREFA.value,
            Notificacao.uae == uae,
            Notificacao.tipo == tipo,
            Notificacao.chave_dedupe == chave_dedupe,
            Notificacao.resolved_at.is_(None),
        )
        .values(
            resolved_by=resolved_by,
            resolved_at=datetime.now(timezone.utc),
        )
    )
    return result.rowcount
