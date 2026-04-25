import json
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.orcamento import OrcamentoAnual
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.schemas.cegep.orcamento import (
    OrcamentoAnualCreate,
    OrcamentoAnualOut,
    OrcamentoAnualUpdate,
    OrcamentoLogOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import get_current_user
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/orcamento', tags=['CEGEP'])

RESOURCE = 'orcamento_anual'


def _orcamento_to_dict(orc: OrcamentoAnual) -> dict:
    return {
        'ano_ref': orc.ano_ref,
        'total': float(orc.total),
        'abertura': float(orc.abertura),
        'fechamento': float(orc.fechamento),
    }


@router.get('/', response_model=ApiResponse[OrcamentoAnualOut | None])
async def get_orcamento(
    session: Session,
    ano: int,
):
    """Retorna o orçamento anual do ano escolhido (ou null se não existir)."""
    orc = await session.scalar(
        select(OrcamentoAnual).where(OrcamentoAnual.ano_ref == ano)
    )
    return success_response(data=orc)


@router.post(
    '/',
    response_model=ApiResponse[OrcamentoAnualOut],
    status_code=HTTPStatus.CREATED,
)
async def create_orcamento(
    payload: OrcamentoAnualCreate,
    session: Session,
    current_user: CurrentUser,
):
    existing = await session.scalar(
        select(OrcamentoAnual).where(OrcamentoAnual.ano_ref == payload.ano_ref)
    )
    if existing:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Já existe um orçamento cadastrado para este exercício.',
        )

    new_orc = OrcamentoAnual(
        ano_ref=payload.ano_ref,
        total=payload.total,
        abertura=payload.abertura,
        fechamento=payload.fechamento,
    )
    session.add(new_orc)
    await session.flush()

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='create',
        resource=RESOURCE,
        resource_id=new_orc.id,
        before=None,
        after=_orcamento_to_dict(new_orc),
    )

    await session.commit()
    await session.refresh(new_orc)

    return success_response(data=new_orc)


@router.put('/{orc_id}', response_model=ApiResponse[OrcamentoAnualOut])
async def update_orcamento(
    orc_id: int,
    payload: OrcamentoAnualUpdate,
    session: Session,
    current_user: CurrentUser,
):
    db_orc = await session.scalar(
        select(OrcamentoAnual).where(OrcamentoAnual.id == orc_id)
    )
    if not db_orc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Orçamento não encontrado',
        )

    if db_orc.ano_ref != payload.ano_ref:
        conflict = await session.scalar(
            select(OrcamentoAnual).where(
                OrcamentoAnual.ano_ref == payload.ano_ref,
                OrcamentoAnual.id != orc_id,
            )
        )
        if conflict:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'Já existe um orçamento cadastrado para este exercício.'
                ),
            )

    before = _orcamento_to_dict(db_orc)

    db_orc.ano_ref = payload.ano_ref
    db_orc.total = payload.total
    db_orc.abertura = payload.abertura
    db_orc.fechamento = payload.fechamento

    await session.flush()

    after = _orcamento_to_dict(db_orc)

    if before != after:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE,
            resource_id=db_orc.id,
            before=before,
            after=after,
        )

    await session.commit()
    await session.refresh(db_orc)

    return success_response(data=db_orc)


@router.get(
    '/{orc_id}/logs',
    response_model=ApiResponse[list[OrcamentoLogOut]],
)
async def list_orcamento_logs(
    orc_id: int,
    session: Session,
):
    db_orc = await session.scalar(
        select(OrcamentoAnual).where(OrcamentoAnual.id == orc_id)
    )
    if not db_orc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Orçamento não encontrado',
        )

    query = (
        select(UserActionLog)
        .options(selectinload(UserActionLog.user))
        .where(
            UserActionLog.resource == RESOURCE,
            UserActionLog.resource_id == orc_id,
        )
        .order_by(UserActionLog.timestamp.desc(), UserActionLog.id.desc())
        .limit(100)
    )

    result = await session.scalars(query)
    logs = result.all()

    payload = []
    for log in logs:
        try:
            before = json.loads(log.before) if log.before else None
        except (json.JSONDecodeError, TypeError):
            before = None
        try:
            after = json.loads(log.after) if log.after else None
        except (json.JSONDecodeError, TypeError):
            after = None
        payload.append({
            'id': log.id,
            'user': log.user,
            'action': log.action,
            'before': before,
            'after': after,
            'timestamp': log.timestamp,
        })

    return success_response(data=payload)
