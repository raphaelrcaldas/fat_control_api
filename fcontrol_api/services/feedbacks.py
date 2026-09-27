"""Leitura da conversa de feedback, compartilhada pelos dois routers.

O autor (`routers/feedbacks.py`) e a administração
(`routers/admin/feedbacks.py`) enxergam o MESMO resumo e o MESMO detalhe;
só o recorte de quem pode ver muda, e esse fica no router.

A lista calcula o resumo em lote — uma contagem e uma "última mensagem"
por feedback, em duas consultas no total — para nunca carregar as
conversas inteiras nem consultar item a item.

Também avisa a administração (`avisar_admins`): feedback novo e mensagem
do autor chegam no sino do client de cada admin de sistema.
"""

from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.enums.feedback import FeedbackEventoTipoEnum
from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.security.resources import Roles, UserRole
from fcontrol_api.models.shared.feedback import Feedback, FeedbackEvento
from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.schemas.feedback import (
    FeedbackBaseOut,
    FeedbackDetalheOut,
    FeedbackEventoOut,
    FeedbackOut,
    FeedbackUserOut,
)
from fcontrol_api.services.auth import FATBIRD_CLIENT
from fcontrol_api.services.notificacoes import notificar_usuarios

# Recurso das notificações de conversa. NÃO é `feedbacks`: esse foi um
# recurso RBAC removido, e o nome igual confundiria quem busca permissão.
RECURSO_NOTIF = 'shared.feedback'

MENSAGEM = FeedbackEventoTipoEnum.MENSAGEM.value


def origem_do_app(app_client: str | None) -> str:
    """Deriva a origem do `app_client` do TOKEN, nunca do request.

    Mesmo racional de `audiencia_do_app`: o front não escolhe o que
    grava nem o que enxerga. Reusada nos quatro endpoints do autor: grava
    no `POST /` e filtra `Feedback.origem` no `WHERE` dos outros três
    (`/me`, `GET /{id}`, `POST /{id}/mensagens`).
    """
    return 'fatbird' if app_client == FATBIRD_CLIENT else 'client'


def audiencia_da_origem(origem: str) -> str:
    """Em qual sino a conversa avisa, a partir da ORIGEM do feedback.

    Espelha `audiencia_do_app` do lado da emissão: a conversa nasceu no
    FatBird avisa o tripulante nele; a que nasceu no client avisa o
    gestor no client. Cada app só ganha sino para as conversas que
    começaram nele — não pelo `app_client` de quem está escrevendo agora
    (é sempre a administração), mas pela origem congelada no feedback.
    """
    return (
        NotifAudiencia.TRIPULANTE.value
        if origem == 'fatbird'
        else NotifAudiencia.GESTOR.value
    )


def evento_out(
    evento: FeedbackEvento, autor_do_feedback: int
) -> FeedbackEventoOut:
    return FeedbackEventoOut(
        id=evento.id,
        tipo=evento.tipo,
        texto=evento.texto,
        status=evento.status,
        autor=(
            FeedbackUserOut.model_validate(evento.autor)
            if evento.autor
            else None
        ),
        do_autor=evento.autor_id == autor_do_feedback,
        created_at=evento.created_at,
    )


def _com_resumo(
    feedback: Feedback, total: int, ultima: FeedbackEvento | None
) -> FeedbackOut:
    return FeedbackOut(
        **FeedbackBaseOut.model_validate(feedback).model_dump(),
        total_mensagens=total,
        ultima_mensagem=(
            evento_out(ultima, feedback.user_id) if ultima else None
        ),
        ultima_atividade=ultima.created_at if ultima else feedback.created_at,
    )


async def listar_com_resumo(
    session: AsyncSession, query: Select[tuple[Feedback]]
) -> list[FeedbackOut]:
    """Resumo de cada feedback da `query`, mais recente atividade antes."""
    feedbacks = (await session.scalars(query)).all()
    ids = [f.id for f in feedbacks]
    if not ids:
        return []

    mensagens_dos_ids = (
        FeedbackEvento.feedback_id.in_(ids),
        FeedbackEvento.tipo == MENSAGEM,
    )
    contagens = dict(
        (
            await session.execute(
                select(FeedbackEvento.feedback_id, func.count())
                .where(*mensagens_dos_ids)
                .group_by(FeedbackEvento.feedback_id)
            )
        ).all()
    )
    # DISTINCT ON do Postgres: uma linha por feedback, a mais recente.
    ultimas = {
        e.feedback_id: e
        for e in (
            await session.scalars(
                select(FeedbackEvento)
                .where(*mensagens_dos_ids)
                .distinct(FeedbackEvento.feedback_id)
                .order_by(
                    FeedbackEvento.feedback_id,
                    FeedbackEvento.created_at.desc(),
                    FeedbackEvento.id.desc(),
                )
            )
        ).all()
    }

    resumos = [
        _com_resumo(f, contagens.get(f.id, 0), ultimas.get(f.id))
        for f in feedbacks
    ]
    resumos.sort(key=lambda r: (r.ultima_atividade, r.id), reverse=True)
    return resumos


async def detalhe_feedback(
    session: AsyncSession, feedback: Feedback
) -> FeedbackDetalheOut:
    eventos = (
        await session.scalars(
            select(FeedbackEvento)
            .where(FeedbackEvento.feedback_id == feedback.id)
            .order_by(FeedbackEvento.created_at, FeedbackEvento.id)
        )
    ).all()
    mensagens = [e for e in eventos if e.tipo == MENSAGEM]
    resumo = _com_resumo(
        feedback, len(mensagens), mensagens[-1] if mensagens else None
    )
    return FeedbackDetalheOut(
        **resumo.model_dump(),
        eventos=[evento_out(e, feedback.user_id) for e in eventos],
    )


async def avisar_admins(
    session: AsyncSession, feedback: Feedback, *, tipo: NotifTipo
) -> None:
    """Avisa cada admin de SISTEMA no sino do client, sem commit.

    `FEEDBACK_RECEBIDO` no envio; `FEEDBACK_MENSAGEM_AUTOR` quando o autor
    escreve na conversa. O destinatário é quem tem vínculo admin sem
    organização (`organizacao_id IS NULL`) — o mesmo critério de
    `security.is_system_admin`, sem a exigência de contexto: a caixa é
    tratada no contexto Sistema, mas o aviso é da pessoa e aparece em
    qualquer contexto (o client troca para Sistema ao abrir).

    Audiência sempre `gestor`: o painel `/admin/feedback` só existe no
    client, qualquer que seja a origem do feedback. O autor que também é
    admin não se avisa (`notificar_usuarios` pula `created_by`, e o
    agrupamento abaixo o exclui do alvo).

    Um item por feedback no sino de cada admin enquanto não é lido: a
    mensagem do autor sobre um aviso ainda não lido (de feedback novo ou de
    mensagem anterior) só o renova e sobe ao topo — em vez de empilhar
    itens do mesmo feedback. Só a mensagem sobre outra mensagem soma `qtd`
    no título; sobre o "feedback recebido" o título continua dizendo que
    ele é novo, que é o que importa a quem ainda não o abriu.
    """
    admins = (
        await session.scalars(
            select(UserRole.user_id)
            .join(Roles, Roles.id == UserRole.role_id)
            .where(
                UserRole.organizacao_id.is_(None),
                func.lower(Roles.name) == 'admin',
                UserRole.user_id != feedback.user_id,
            )
        )
    ).all()
    if not admins:
        return

    audiencia = NotifAudiencia.GESTOR.value
    alvos = list(admins)
    if tipo == NotifTipo.FEEDBACK_MENSAGEM_AUTOR:
        pendentes = (
            await session.scalars(
                select(Notificacao).where(
                    Notificacao.user_id.in_(alvos),
                    Notificacao.escopo == NotifEscopo.DIRETA.value,
                    Notificacao.audiencia == audiencia,
                    Notificacao.tipo.in_([
                        NotifTipo.FEEDBACK_RECEBIDO.value,
                        NotifTipo.FEEDBACK_MENSAGEM_AUTOR.value,
                    ]),
                    Notificacao.recurso == RECURSO_NOTIF,
                    Notificacao.recurso_id == feedback.id,
                    Notificacao.read_at.is_(None),
                )
            )
        ).all()
        agora = datetime.now(timezone.utc)
        for pendente in pendentes:
            if pendente.tipo == NotifTipo.FEEDBACK_MENSAGEM_AUTOR.value:
                qtd = int(pendente.payload.get('qtd', 1)) + 1
                # Reatribui o dict: JSONB não rastreia mutação in-place.
                pendente.payload = {**pendente.payload, 'qtd': qtd}
                pendente.titulo = f'{qtd} novas mensagens do autor'
            pendente.created_at = agora
        avisados = {p.user_id for p in pendentes}
        alvos = [uid for uid in alvos if uid not in avisados]

    await notificar_usuarios(
        session,
        user_ids=alvos,
        uae=feedback.uae,
        audiencia=audiencia,
        tipo=tipo.value,
        titulo=(
            'Novo feedback recebido'
            if tipo == NotifTipo.FEEDBACK_RECEBIDO
            else 'Nova mensagem do autor'
        ),
        descricao=feedback.titulo,
        recurso=RECURSO_NOTIF,
        recurso_id=feedback.id,
        payload=(
            {'qtd': 1} if tipo == NotifTipo.FEEDBACK_MENSAGEM_AUTOR else None
        ),
        created_by=feedback.user_id,
    )
