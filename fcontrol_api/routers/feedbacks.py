"""Feedbacks e sugestões enviados pelo portal (FatBird).

Este router é o lado do AUTOR: enviar e acompanhar o que enviou. Ambos os
endpoints são abertos a qualquer usuário autenticado — o canal só existe se
a tropa puder usá-lo, e tripulante não tem role no backend (ver o FatBird,
que reusa endpoints administrativos).

O TRATAMENTO (ler a caixa, responder, mover status) mora em
`routers/admin/feedbacks.py`: é control-plane de sistema, gateado pelo
`require_system_admin` do grupo `/admin`.

Escopo: `uae` é congelado no envio a partir da org ativa de quem enviou —
o feedback fica com a unidade que o recebeu mesmo se o autor for
movimentado depois.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.feedback import Feedback
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.feedback import FeedbackCreate, FeedbackOut
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, get_current_user
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
    criado = await session.scalar(
        select(Feedback).where(Feedback.id == feedback.id)
    )

    if not criado:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Feedback não encontrado',
        )

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
