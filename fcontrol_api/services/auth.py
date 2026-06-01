from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import (
    Permissions,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.models.shared.tripulantes import Tripulante

Session = Annotated[AsyncSession, Depends(get_session)]


async def resolve_default_org(
    user_id: int, session: AsyncSession
) -> str | None:
    """Define a org ativa padrão no login.

    Prioriza o vínculo de sistema (organizacao_id NULL); na ausência dele,
    escolhe o vínculo de menor organizacao_id (determinístico).
    """
    return await session.scalar(
        select(UserRole.organizacao_id)
        .where(UserRole.user_id == user_id)
        .order_by(UserRole.organizacao_id.asc().nulls_first())
        .limit(1)
    )


async def get_user_roles(
    user_id: int,
    session: Session,
    active_org: str | None = None,
):
    role_data = {'role': None, 'perms': []}

    perms_load = (
        joinedload(UserRole.role)
        .joinedload(Roles.permissions)
        .joinedload(RolePermissions.permission)
        .joinedload(Permissions.resource)
    )

    query = (
        select(UserRole)
        .where(
            UserRole.user_id == user_id,
            UserRole.organizacao_id.is_not_distinct_from(active_org),
        )
        .options(perms_load)
    )

    result = await session.scalar(query)

    # Fallback: token sem claim (antigo) ou org inexistente -> primeiro
    # vínculo do usuário, evitando travar a autenticação na transição.
    if not result:
        result = await session.scalar(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(
                UserRole.organizacao_id.asc().nulls_first(), UserRole.id
            )
            .options(perms_load)
        )

    if not result:
        return role_data

    user_role = result.role
    perms = [
        {
            'resource': perm.permission.resource.name,
            'name': perm.permission.name,
        }
        for perm in user_role.permissions
    ]

    role_data['role'] = user_role.name
    role_data['perms'] = perms

    return role_data


async def validate_user_client_access(
    user_id: int, client_id: str, session: AsyncSession
) -> None:
    """
    Valida se usuário tem permissões mínimas para acessar o cliente.

    Regras de negócio baseadas em Zero Trust:
    - FATCONTROL: usuário deve ter pelo menos uma role cadastrada
    - FATBIRD: usuário deve ser um tripulante ativo

    Args:
        user_id: ID do usuário a ser validado
        client_id: ID do cliente OAuth2 (fatcontrol ou fatbird)
        session: Sessão do banco de dados

    Raises:
        HTTPException (403): Se não atender os requisitos mínimos
    """
    if client_id == 'fatcontrol':
        # FATCONTROL: usuário deve ter pelo menos uma role cadastrada
        user_role = await session.scalar(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        if not user_role:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail='Usuário sem permissões cadastradas para o FATCONTROL',
            )
    elif client_id == 'fatbird':
        # FATBIRD: usuário deve ser um tripulante ativo
        tripulante = await session.scalar(
            select(Tripulante).where(
                Tripulante.user_id == user_id, Tripulante.active
            )
        )
        if not tripulante:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail='Apenas tripulantes ativos podem acessar o FATBIRD',
            )
