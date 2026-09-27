"""Tratamento dos feedbacks do portal — control-plane de SISTEMA.

A caixa é cross-tenant: o admin de sistema (contexto Sistema, `active_org`
NULL) lê o que veio de todas as unidades e responde ao autor. Por isso não
há filtro por `uae` aqui — a coluna continua no dado, congelada no envio,
e é o que diz de qual unidade cada feedback saiu.

O gate `require_system_admin` é declarado uma única vez no grupo
(`routers/admin/__init__.py`); este router não repete a dependência. Não há
recurso RBAC de feedbacks: o acesso é por escopo de sistema, não por
permissão concedível a uma role de unidade.

O envio e o acompanhamento pelo próprio autor ficam em
`routers/feedbacks.py`, abertos a qualquer autenticado.

A administração conversa com o autor: cada mensagem dela avisa o autor no
sino do app onde a conversa NASCEU — a `origem` do feedback, não o
`app_client` de quem está respondendo agora, que é sempre a administração.
`origem='fatbird'` avisa audiência `tripulante` no FatBird;
`origem='client'` avisa audiência `gestor` no client. Agrupa num aviso só
enquanto o anterior não foi lido, sem misturar os dois apps. Mudança de
status entra na linha do tempo, mas não avisa.

No sentido inverso, o envio e cada mensagem do autor avisam os admins de
sistema (`services/feedbacks.avisar_admins`, chamado pelo router do autor).
"""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.enums.feedback import (
    FeedbackEventoTipoEnum,
    FeedbackStatusEnum,
    FeedbackTipoEnum,
)
from fcontrol_api.enums.notificacao import NotifEscopo, NotifTipo
from fcontrol_api.models.shared.feedback import Feedback, FeedbackEvento
from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.feedback import (
    FeedbackAdminMensagemCreate,
    FeedbackDetalheOut,
    FeedbackOut,
    FeedbackUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import get_current_user
from fcontrol_api.services.feedbacks import (
    RECURSO_NOTIF,
    audiencia_da_origem,
    detalhe_feedback,
    listar_com_resumo,
)
from fcontrol_api.services.notificacoes import notificar_usuarios
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/feedbacks', tags=['Admin - Feedbacks'])


async def _get_feedback(session: AsyncSession, feedback_id: int) -> Feedback:
    """Feedback pelo id (sem recorte de org: a caixa é de sistema)."""
    feedback = await session.scalar(
        select(Feedback).where(Feedback.id == feedback_id)
    )

    if not feedback:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Feedback não encontrado',
        )

    return feedback


@router.get('/', response_model=ApiResponse[list[FeedbackOut]])
async def list_feedbacks(
    session: Session,
    status: Annotated[FeedbackStatusEnum | None, Query()] = None,
    tipo: Annotated[FeedbackTipoEnum | None, Query()] = None,
    uae: Annotated[str | None, Query()] = None,
):
    """Caixa de entrada de todas as unidades."""
    query = select(Feedback)

    if status:
        query = query.where(Feedback.status == status.value)

    if tipo:
        query = query.where(Feedback.tipo == tipo.value)

    if uae:
        query = query.where(Feedback.uae == uae)

    return success_response(data=await listar_com_resumo(session, query))


@router.get('/{feedback_id}', response_model=ApiResponse[FeedbackDetalheOut])
async def get_feedback(feedback_id: int, session: Session):
    """Conversa completa de um feedback."""
    feedback = await _get_feedback(session, feedback_id)
    return success_response(data=await detalhe_feedback(session, feedback))


@router.post(
    '/{feedback_id}/mensagens',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[FeedbackDetalheOut],
)
async def enviar_mensagem(
    feedback_id: int,
    payload: FeedbackAdminMensagemCreate,
    session: Session,
    user: CurrentUser,
):
    """Mensagem ao autor, com troca de status opcional — tudo num commit.

    A mensagem entra antes do evento de status: os dois têm o mesmo
    instante, e o `id` (ordem de inserção) desempata na linha do tempo.
    """
    feedback = await _get_feedback(session, feedback_id)

    session.add(
        FeedbackEvento(
            feedback_id=feedback.id,
            autor_id=user.id,
            tipo=FeedbackEventoTipoEnum.MENSAGEM.value,
            texto=payload.texto,
        )
    )
    if payload.status is not None and payload.status.value != feedback.status:
        feedback.status = payload.status.value
        session.add(
            FeedbackEvento(
                feedback_id=feedback.id,
                autor_id=user.id,
                tipo=FeedbackEventoTipoEnum.STATUS.value,
                status=payload.status.value,
            )
        )

    # Quem escreve não se avisa (o admin no próprio feedback). O serviço
    # já pula `created_by`, mas o agrupamento abaixo não passa por ele.
    if feedback.user_id != user.id:
        audiencia = audiencia_da_origem(feedback.origem)
        # Agrupa enquanto o aviso anterior não foi lido: três mensagens
        # seguidas viram UM item no sino, que sobe ao topo a cada nova.
        # `audiencia` entra no filtro para o aviso de um app nunca
        # agrupar com o do outro — hoje redundante (a origem não muda no
        # feedback), mas mantém a amarra de app local a esta query.
        pendente = await session.scalar(
            select(Notificacao)
            .where(
                Notificacao.user_id == feedback.user_id,
                Notificacao.escopo == NotifEscopo.DIRETA.value,
                Notificacao.audiencia == audiencia,
                Notificacao.tipo == NotifTipo.FEEDBACK_MENSAGEM.value,
                Notificacao.recurso == RECURSO_NOTIF,
                Notificacao.recurso_id == feedback.id,
                Notificacao.read_at.is_(None),
            )
            .order_by(Notificacao.created_at.desc())
            .limit(1)
        )
        if pendente:
            qtd = int(pendente.payload.get('qtd', 1)) + 1
            # Reatribui o dict: JSONB não rastreia mutação in-place.
            pendente.payload = {**pendente.payload, 'qtd': qtd}
            pendente.titulo = f'{qtd} novas mensagens no seu feedback'
            pendente.created_at = datetime.now(timezone.utc)
        else:
            await notificar_usuarios(
                session,
                user_ids=[feedback.user_id],
                uae=feedback.uae,
                audiencia=audiencia,
                tipo=NotifTipo.FEEDBACK_MENSAGEM.value,
                titulo='Nova mensagem no seu feedback',
                descricao=feedback.titulo,
                recurso=RECURSO_NOTIF,
                recurso_id=feedback.id,
                payload={'qtd': 1},
                created_by=user.id,
            )

    await session.commit()

    atualizado = await _get_feedback(session, feedback_id)
    return success_response(
        data=await detalhe_feedback(session, atualizado),
        message='Mensagem enviada',
    )


@router.delete('/{feedback_id}', response_model=ApiResponse[None])
async def delete_feedback(feedback_id: int, session: Session):
    """Apaga o registro de vez — a conversa vai junto (CASCADE) e os
    avisos dela também.

    Sem soft delete: o feedback não é dado operacional que se audite depois
    — é mensagem. O que sobra de errado (duplicata, teste, desabafo já
    resolvido) só polui a caixa de quem tria.
    """
    feedback = await _get_feedback(session, feedback_id)

    # `recurso_id` não tem FK: sem isto o autor ficaria com um link morto
    # no sino. O filtro por `recurso` é obrigatório — ids de outros
    # recursos (indisp, quadrinho) colidem com o do feedback.
    await session.execute(
        delete(Notificacao).where(
            Notificacao.recurso == RECURSO_NOTIF,
            Notificacao.recurso_id == feedback.id,
        )
    )

    await session.delete(feedback)
    await session.commit()

    return success_response(message='Feedback excluído')


@router.patch('/{feedback_id}', response_model=ApiResponse[FeedbackDetalheOut])
async def update_feedback(
    feedback_id: int,
    payload: FeedbackUpdate,
    session: Session,
    user: CurrentUser,
):
    """Muda o status. Status igual ao atual não grava nada — a linha do
    tempo não repete "alterado para Aberto". Não avisa o autor."""
    feedback = await _get_feedback(session, feedback_id)

    if payload.status.value != feedback.status:
        feedback.status = payload.status.value
        session.add(
            FeedbackEvento(
                feedback_id=feedback.id,
                autor_id=user.id,
                tipo=FeedbackEventoTipoEnum.STATUS.value,
                status=payload.status.value,
            )
        )
        await session.commit()

    atualizado = await _get_feedback(session, feedback_id)
    return success_response(
        data=await detalhe_feedback(session, atualizado),
        message='Feedback atualizado',
    )
