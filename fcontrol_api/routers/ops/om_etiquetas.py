"""Router para as etiquetas de Ordem de Missão (OM)"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.om import Etiqueta
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.etiquetas import (
    EtiquetaCreate,
    EtiquetaSchema,
    EtiquetaUpdate,
)
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

router = APIRouter(prefix='/om/etiquetas', tags=['ordens-missao'])

# Etiqueta herda a permissão da OM: mesmo recurso `ordem_missao` dos
# guardas de `om.py` — quem edita a ordem administra as etiquetas dela.
CreateOM = Depends(permission_checker('ordem_missao', 'create'))
UpdateOM = Depends(permission_checker('ordem_missao', 'update'))
DeleteOM = Depends(permission_checker('ordem_missao', 'delete'))

# Auditoria. Etiqueta de OM tem recurso próprio: 'etiqueta' já é do CEGEP,
# cuja Etiqueta é outra tabela, com sequência de id independente — filtrar
# por resource+resource_id misturaria as duas entidades.
RESOURCE_ETIQUETA = 'om_etiqueta'


@router.get('/', response_model=ApiResponse[list[EtiquetaSchema]])
async def list_etiquetas(session: Session, active_org: ActiveOrg):
    """Lista as etiquetas da org ativa"""
    result = await session.execute(
        select(Etiqueta)
        .where(Etiqueta.uae == active_org)
        .order_by(Etiqueta.nome)
    )
    return success_response(data=list(result.scalars().all()))


@router.post(
    '/',
    response_model=ApiResponse[EtiquetaSchema],
    status_code=HTTPStatus.CREATED,
)
async def create_etiqueta(
    etiqueta_data: EtiquetaCreate,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    _: Annotated[User, CreateOM],
):
    """Cria uma nova etiqueta"""
    etiqueta = Etiqueta(
        nome=etiqueta_data.nome,
        cor=etiqueta_data.cor,
        descricao=etiqueta_data.descricao,
        uae=active_org,
    )
    session.add(etiqueta)
    await session.flush()  # Para obter o ID usado no log

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='create',
        resource=RESOURCE_ETIQUETA,
        resource_id=etiqueta.id,
        before=None,
        after={
            'nome': etiqueta.nome,
            'cor': etiqueta.cor,
            'descricao': etiqueta.descricao,
        },
    )

    await session.commit()
    await session.refresh(etiqueta)
    return success_response(
        data=EtiquetaSchema.model_validate(etiqueta),
        message='Etiqueta criada com sucesso',
    )


@router.put('/{id}', response_model=ApiResponse[EtiquetaSchema])
async def update_etiqueta(
    id: int,
    etiqueta_data: EtiquetaUpdate,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    _: Annotated[User, UpdateOM],
):
    """Atualiza uma etiqueta existente"""
    etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == id, Etiqueta.uae == active_org)
    )
    if not etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Etiqueta não encontrada'
        )

    before_snapshot = {
        'nome': etiqueta.nome,
        'cor': etiqueta.cor,
        'descricao': etiqueta.descricao,
    }

    update_data = etiqueta_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(etiqueta, key, value)

    after_snapshot = {
        'nome': etiqueta.nome,
        'cor': etiqueta.cor,
        'descricao': etiqueta.descricao,
    }
    if before_snapshot != after_snapshot:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE_ETIQUETA,
            resource_id=etiqueta.id,
            before=before_snapshot,
            after=after_snapshot,
        )

    await session.commit()
    await session.refresh(etiqueta)
    return success_response(
        data=EtiquetaSchema.model_validate(etiqueta),
        message='Etiqueta atualizada com sucesso',
    )


@router.delete(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_etiqueta(
    id: int,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    _: Annotated[User, DeleteOM],
):
    """Remove uma etiqueta"""
    etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == id, Etiqueta.uae == active_org)
    )
    if not etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Etiqueta não encontrada'
        )

    before_snapshot = {
        'nome': etiqueta.nome,
        'cor': etiqueta.cor,
        'descricao': etiqueta.descricao,
    }

    await session.delete(etiqueta)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='delete',
        resource=RESOURCE_ETIQUETA,
        resource_id=id,
        before=before_snapshot,
        after=None,
    )

    await session.commit()
    return success_response(message='Etiqueta removida com sucesso')
