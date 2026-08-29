"""Feedbacks e sugestões enviados pelo portal (FatBird).

Envio é aberto a qualquer usuário autenticado com org ativa — o canal só
existe se a tropa puder usá-lo, e tripulante não tem role no backend (ver
o FatBird, que reusa endpoints administrativos). O que é gateado é o
TRATAMENTO: ler a caixa da unidade exige `feedbacks.view` e responder,
`feedbacks.update`.

Escopo: `uae` é congelado no envio a partir da org ativa de quem enviou, e
toda leitura administrativa filtra por ele. O gate autoriza a ação; o
alvo é escopado aqui na query.
"""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.enums.feedback import FeedbackStatusEnum, FeedbackTipoEnum
from fcontrol_api.models.shared.feedback import Feedback
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.feedback import (
    FeedbackCreate,
    FeedbackOut,
    FeedbackUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    permission_checker,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/feedbacks', tags=['Feedbacks'])

FEEDBACKS = 'feedbacks'
ViewFeedbacks = Depends(permission_checker(FEEDBACKS, 'view'))
UpdateFeedbacks = Depends(permission_checker(FEEDBACKS, 'update'))


async def _get_feedback(session: AsyncSession, feedback_id: int, uae: str):
    """Feedback pelo id, restrito à org ativa (404 fora do escopo)."""
    feedback = await session.scalar(
        select(Feedback).where(
            Feedback.id == feedback_id,
            Feedback.uae == uae,
        )
    )

    if not feedback:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Feedback não encontrado',
        )

    return feedback


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
):
    """Registra um feedback em nome de quem está autenticado."""
    feedback = Feedback(
        user_id=user.id,
        uae=active_org,
        tipo=payload.tipo.value,
        titulo=payload.titulo.strip(),
        descricao=payload.descricao.strip(),
        rota=payload.rota,
    )

    session.add(feedback)
    await session.commit()

    # Recarrega pela query (e não `refresh`) para trazer o relacionamento
    # `autor` que o schema de saída exige.
    criado = await _get_feedback(session, feedback.id, active_org)

    return success_response(
        data=FeedbackOut.model_validate(criado),
        message='Feedback enviado. Obrigado!',
    )


@router.get('/me', response_model=ApiResponse[list[FeedbackOut]])
async def list_meus_feedbacks(session: Session, user: CurrentUser):
    """Feedbacks do próprio usuário, de todas as orgs em que ele enviou.

    Self-service: não passa por gate nem por org ativa — é o dado de quem
    está pedindo, e quem trocou de unidade continua acompanhando o que
    mandou antes.
    """
    feedbacks = (
        await session.scalars(
            select(Feedback)
            .where(Feedback.user_id == user.id)
            .order_by(Feedback.created_at.desc())
        )
    ).all()

    return success_response(
        data=[FeedbackOut.model_validate(f) for f in feedbacks]
    )


@router.get(
    '/',
    response_model=ApiResponse[list[FeedbackOut]],
    dependencies=[ViewFeedbacks],
)
async def list_feedbacks(
    session: Session,
    active_org: ActiveOrg,
    status: Annotated[FeedbackStatusEnum | None, Query()] = None,
    tipo: Annotated[FeedbackTipoEnum | None, Query()] = None,
):
    """Caixa de entrada da unidade (org ativa)."""
    query = select(Feedback).where(Feedback.uae == active_org)

    if status:
        query = query.where(Feedback.status == status.value)

    if tipo:
        query = query.where(Feedback.tipo == tipo.value)

    feedbacks = (
        await session.scalars(query.order_by(Feedback.created_at.desc()))
    ).all()

    return success_response(
        data=[FeedbackOut.model_validate(f) for f in feedbacks]
    )


@router.patch(
    '/{feedback_id}',
    response_model=ApiResponse[FeedbackOut],
    dependencies=[UpdateFeedbacks],
)
async def update_feedback(
    feedback_id: int,
    payload: FeedbackUpdate,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
):
    """Move o status e/ou responde ao autor."""
    feedback = await _get_feedback(session, feedback_id, active_org)

    if payload.status is not None:
        feedback.status = payload.status.value

    if payload.resposta is not None:
        # String vazia limpa a resposta (e a autoria junto): o formulário
        # do painel manda o campo inteiro, então apagar o texto é o gesto
        # natural de "retirar o que respondi".
        resposta = payload.resposta.strip()
        feedback.resposta = resposta or None
        feedback.respondido_por = user.id if resposta else None
        feedback.respondido_em = (
            datetime.now(timezone.utc) if resposta else None
        )

    await session.commit()

    atualizado = await _get_feedback(session, feedback_id, active_org)

    return success_response(
        data=FeedbackOut.model_validate(atualizado),
        message='Feedback atualizado',
    )
