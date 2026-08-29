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
from fcontrol_api.schemas.feedback import FeedbackOut, FeedbackUpdate
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import get_current_user
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

    feedbacks = (
        await session.scalars(query.order_by(Feedback.created_at.desc()))
    ).all()

    return success_response(
        data=[FeedbackOut.model_validate(f) for f in feedbacks]
    )


@router.patch('/{feedback_id}', response_model=ApiResponse[FeedbackOut])
async def update_feedback(
    feedback_id: int,
    payload: FeedbackUpdate,
    session: Session,
    user: CurrentUser,
):
    """Move o status e/ou responde ao autor."""
    feedback = await _get_feedback(session, feedback_id)

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

    atualizado = await _get_feedback(session, feedback_id)

    return success_response(
        data=FeedbackOut.model_validate(atualizado),
        message='Feedback atualizado',
    )
