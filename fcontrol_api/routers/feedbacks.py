"""Feedbacks e sugestões enviados pelo portal (FatBird).

Este router é o lado do AUTOR. Os endpoints são abertos a qualquer usuário
autenticado — o canal só existe se a tropa puder usá-lo, e tripulante não
tem role no backend (ver o FatBird, que reusa endpoints administrativos):
enviar um feedback, ler a conversa de um feedback seu e escrever nela (só
leitura quando o status é `concluido`/`recusado`).

O TRATAMENTO (ler a caixa, responder, mover status) mora em
`routers/admin/feedbacks.py`: é control-plane de sistema, gateado pelo
`require_system_admin` do grupo `/admin`. O envio e cada mensagem do autor
avisam os admins de sistema no sino do client (`avisar_admins`).

Escopo: `uae` é congelado no envio a partir da org ativa de quem enviou —
o feedback fica com a unidade que o recebeu mesmo se o autor for
movimentado depois.

Separação por app: `origem` também é derivada do `app_client` do token no
envio (`origem_do_app`) e entra no filtro dos três endpoints — o autor só
enxerga, no `/me`, no `GET /{id}` e no `POST /{id}/mensagens`, os
feedbacks enviados pelo app em que está logado agora; feedback de outro
app responde o mesmo 404 de inexistente. A caixa do admin não filtra por
origem (vê tudo).
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.enums.feedback import (
    STATUS_ENCERRADOS,
    FeedbackEventoTipoEnum,
)
from fcontrol_api.enums.notificacao import NotifTipo
from fcontrol_api.models.shared.feedback import Feedback, FeedbackEvento
from fcontrol_api.models.shared.users import User
from fcontrol_api.routers.notificacoes import AppClient
from fcontrol_api.schemas.feedback import (
    FeedbackCreate,
    FeedbackDetalheOut,
    FeedbackEventoOut,
    FeedbackMensagemCreate,
    FeedbackOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, get_current_user
from fcontrol_api.services.feedbacks import (
    avisar_admins,
    detalhe_feedback,
    evento_out,
    listar_com_resumo,
    origem_do_app,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/feedbacks', tags=['Feedbacks'])


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[FeedbackOut],
)
async def create_feedback(
    payload: FeedbackCreate,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
    app_client: AppClient,
):
    """Registra um feedback em nome de quem está autenticado e avisa a
    administração."""
    feedback = Feedback(
        user_id=user.id,
        uae=active_org,
        tipo=payload.tipo.value,
        titulo=payload.titulo.strip(),
        descricao=payload.descricao.strip(),
        rota=payload.rota,
        origem=origem_do_app(app_client),
    )

    session.add(feedback)
    # O aviso aponta para o `id`, que só existe depois do flush; o commit
    # é um só — sem feedback gravado, não há aviso.
    await session.flush()
    await avisar_admins(session, feedback, tipo=NotifTipo.FEEDBACK_RECEBIDO)
    await session.commit()

    return success_response(
        data=(
            await listar_com_resumo(
                session, select(Feedback).where(Feedback.id == feedback.id)
            )
        )[0],
        message='Feedback enviado. Obrigado!',
    )


@router.get('/me', response_model=ApiResponse[list[FeedbackOut]])
async def list_meus_feedbacks(
    session: Session, user: CurrentUser, app_client: AppClient
):
    """Feedbacks do próprio usuário, de todas as orgs em que ele enviou.

    Self-service: não passa por gate nem por org ativa — é o dado de quem
    está pedindo, e quem trocou de unidade continua acompanhando o que
    mandou antes. Filtra também por `origem`: o app em que está logado
    agora não vê o que foi enviado pelo outro.
    """
    return success_response(
        data=await listar_com_resumo(
            session,
            select(Feedback).where(
                Feedback.user_id == user.id,
                Feedback.origem == origem_do_app(app_client),
            ),
        )
    )


@router.get(
    '/{feedback_id:int}', response_model=ApiResponse[FeedbackDetalheOut]
)
async def get_meu_feedback(
    feedback_id: int,
    session: Session,
    user: CurrentUser,
    app_client: AppClient,
):
    """Conversa de um feedback do próprio usuário (sem recorte de org,
    como o `/me`: é dado da pessoa)."""
    # Outro dono, outro app e inexistente recebem o mesmo 404: responder
    # 403 revelaria que o id existe.
    feedback = await session.scalar(
        select(Feedback).where(
            Feedback.id == feedback_id,
            Feedback.user_id == user.id,
            Feedback.origem == origem_do_app(app_client),
        )
    )
    if not feedback:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Feedback não encontrado',
        )
    return success_response(data=await detalhe_feedback(session, feedback))


@router.post(
    '/{feedback_id:int}/mensagens',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[FeedbackEventoOut],
)
async def enviar_mensagem(
    feedback_id: int,
    payload: FeedbackMensagemCreate,
    session: Session,
    user: CurrentUser,
    app_client: AppClient,
):
    """O autor escreve na conversa e avisa a administração."""
    feedback = await session.scalar(
        select(Feedback).where(
            Feedback.id == feedback_id,
            Feedback.user_id == user.id,
            Feedback.origem == origem_do_app(app_client),
        )
    )
    if not feedback:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Feedback não encontrado',
        )

    if feedback.status in STATUS_ENCERRADOS:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Esta conversa foi encerrada',
        )

    evento = FeedbackEvento(
        feedback_id=feedback.id,
        autor_id=user.id,
        tipo=FeedbackEventoTipoEnum.MENSAGEM.value,
        texto=payload.texto,
    )
    session.add(evento)
    await avisar_admins(
        session, feedback, tipo=NotifTipo.FEEDBACK_MENSAGEM_AUTOR
    )
    await session.commit()

    # Recarrega pela query para trazer o relacionamento `autor`.
    criado = await session.scalar(
        select(FeedbackEvento).where(FeedbackEvento.id == evento.id)
    )
    return success_response(
        data=evento_out(criado, feedback.user_id),
        message='Mensagem enviada',
    )
