"""Router para as etiquetas de missão do CEGEP"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import Etiqueta
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.etiquetas import EtiquetaInput, EtiquetaSchema
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/missoes/etiquetas', tags=['CEGEP'])

RESOURCE_ETIQUETA = 'etiqueta'

# Etiqueta herda o recurso da missão: mesmos guardas de `missao.py`.
ViewMis = Depends(permission_checker('missoes_cegep', 'view'))
CreateMis = Depends(permission_checker('missoes_cegep', 'create'))
DeleteMis = Depends(permission_checker('missoes_cegep', 'delete'))


@router.get(
    '',
    response_model=ApiResponse[list[EtiquetaSchema]],
    dependencies=[ViewMis],
)
async def get_etiquetas(session: Session, active_org: ActiveOrg):
    """Lista as etiquetas da org ativa"""
    stmt = (
        select(Etiqueta)
        .where(Etiqueta.uae == active_org)
        .order_by(Etiqueta.nome)
    )
    db_etiquetas = (await session.scalars(stmt)).all()
    return success_response(data=list(db_etiquetas))


@router.post(
    '',
    response_model=ApiResponse[EtiquetaSchema],
    dependencies=[CreateMis],
)
async def create_or_update_etiqueta(
    payload: EtiquetaInput,
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
):
    """Cria ou atualiza uma etiqueta"""
    before_snapshot: dict | None = None

    if payload.id:
        # Atualização (escopada: etiqueta de outra org -> 404)
        db_etiqueta = await session.scalar(
            select(Etiqueta).where(
                Etiqueta.id == payload.id, Etiqueta.uae == active_org
            )
        )
        if not db_etiqueta:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail='Etiqueta não encontrada',
            )
        before_snapshot = {
            'nome': db_etiqueta.nome,
            'cor': db_etiqueta.cor,
            'descricao': db_etiqueta.descricao,
        }
        db_etiqueta.nome = payload.nome
        db_etiqueta.cor = payload.cor
        db_etiqueta.descricao = payload.descricao
        msg = 'Etiqueta atualizada com sucesso'
    else:
        # Criação
        db_etiqueta = Etiqueta(
            nome=payload.nome,
            cor=payload.cor,
            descricao=payload.descricao,
            uae=active_org,
        )
        session.add(db_etiqueta)
        await session.flush()
        msg = 'Etiqueta criada com sucesso'

    after_snapshot = {
        'nome': db_etiqueta.nome,
        'cor': db_etiqueta.cor,
        'descricao': db_etiqueta.descricao,
    }

    if payload.id:
        if before_snapshot != after_snapshot:
            await log_user_action(
                session=session,
                user_id=current_user.id,
                action='update',
                resource=RESOURCE_ETIQUETA,
                resource_id=db_etiqueta.id,
                before=before_snapshot,
                after=after_snapshot,
            )
    else:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='create',
            resource=RESOURCE_ETIQUETA,
            resource_id=db_etiqueta.id,
            before=None,
            after=after_snapshot,
        )

    await session.commit()
    await session.refresh(db_etiqueta)

    return success_response(
        data=EtiquetaSchema.model_validate(db_etiqueta),
        message=msg,
    )


@router.delete(
    '/{etiqueta_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteMis],
)
async def delete_etiqueta(
    etiqueta_id: int,
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
):
    """Remove uma etiqueta"""
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(
            Etiqueta.id == etiqueta_id, Etiqueta.uae == active_org
        )
    )
    if not db_etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etiqueta não encontrada',
        )

    before_snapshot = {
        'nome': db_etiqueta.nome,
        'cor': db_etiqueta.cor,
        'descricao': db_etiqueta.descricao,
    }

    await session.delete(db_etiqueta)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='delete',
        resource=RESOURCE_ETIQUETA,
        resource_id=etiqueta_id,
        before=before_snapshot,
        after=None,
    )

    await session.commit()

    return success_response(message='Etiqueta removida com sucesso')
