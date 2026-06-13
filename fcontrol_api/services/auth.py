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
from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.schemas.users import OrgScope

Session = Annotated[AsyncSession, Depends(get_session)]

# Cliente OAuth do portal de tripulantes. Para ele, o escopo de
# organização vem da lotação em `tripulantes` (não de `user_roles`).
FATBIRD_CLIENT = 'fatbird'


async def resolve_default_org(
    user_id: int, session: AsyncSession, app_client: str | None = None
) -> str | None:
    """Define a org ativa padrão no login.

    No FATBIRD (portal de tripulantes), a org vem da lotação em
    `tripulantes`: escolhe a sigla de menor valor (determinístico).
    Nos demais clientes, prioriza o vínculo de sistema (organizacao_id
    NULL) e, na ausência dele, o vínculo de menor organizacao_id.
    """
    if app_client == FATBIRD_CLIENT:
        return await session.scalar(
            select(Tripulante.uae)
            .where(Tripulante.user_id == user_id, Tripulante.active)
            .order_by(Tripulante.uae.asc())
            .limit(1)
        )

    return await session.scalar(
        select(UserRole.organizacao_id)
        .where(UserRole.user_id == user_id)
        .order_by(UserRole.organizacao_id.asc().nulls_first())
        .limit(1)
    )


async def user_has_org_access(
    user_id: int,
    org: str | None,
    session: AsyncSession,
    app_client: str | None = None,
) -> bool:
    """Valida se o usuário pode assumir a org `org` no contexto do cliente.

    FATBIRD: precisa ter lotação ativa como tripulante naquela sigla.
    Demais: precisa de um vínculo (UserRole) na org (NULL = sistema).
    """
    if app_client == FATBIRD_CLIENT:
        found = await session.scalar(
            select(Tripulante.id).where(
                Tripulante.user_id == user_id,
                Tripulante.active,
                Tripulante.uae == org,
            )
        )
        return found is not None

    found = await session.scalar(
        select(UserRole.id).where(
            UserRole.user_id == user_id,
            UserRole.organizacao_id.is_not_distinct_from(org),
        )
    )
    return found is not None


async def list_user_orgs(
    user_id: int, session: AsyncSession, app_client: str | None = None
) -> list[OrgScope]:
    """Lista os escopos de org disponíveis ao usuário no cliente atual.

    FATBIRD: um escopo por lotação de tripulante (role = trigrama).
    Demais: um escopo por vínculo (UserRole), com o nome do papel.
    """
    if app_client == FATBIRD_CLIENT:
        rows = await session.execute(
            select(
                Tripulante.uae,
                Organizacao.sigla,
                Organizacao.nome,
                Tripulante.trig,
            )
            .outerjoin(Organizacao, Organizacao.sigla == Tripulante.uae)
            .where(Tripulante.user_id == user_id, Tripulante.active)
            .order_by(Tripulante.uae.asc())
        )
        return [
            OrgScope(organizacao_id=uae, sigla=sigla, nome=nome, role=trig)
            for uae, sigla, nome, trig in rows.all()
        ]

    rows = await session.execute(
        select(
            UserRole.organizacao_id,
            Organizacao.sigla,
            Organizacao.nome,
            Roles.name,
        )
        .join(Roles, Roles.id == UserRole.role_id)
        .outerjoin(Organizacao, Organizacao.sigla == UserRole.organizacao_id)
        .where(UserRole.user_id == user_id)
        .order_by(UserRole.organizacao_id.asc().nulls_first())
    )
    return [
        OrgScope(organizacao_id=oid, sigla=sigla, nome=nome, role=role)
        for oid, sigla, nome, role in rows.all()
    ]


async def get_user_roles(
    user_id: int,
    session: Session,
    active_org: str | None = None,
    app_client: str | None = None,
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

    # Fallback: token sem claim (antigo) -> primeiro vínculo do usuário,
    # evitando travar a autenticação na transição.
    # NÃO aplica quando o token traz org explícita: sem vínculo nela
    # (ex.: revogado após a emissão), resolver outro vínculo emprestaria
    # role/permissões de OUTRA organização ao contexto ativo.
    # Tampouco ao FATBIRD: a org do crew vem da lotação (tripulantes),
    # que não corresponde a `user_roles`; cair no fallback resolveria um
    # vínculo não relacionado (ex.: admin de sistema) para o tripulante.
    if not result and active_org is None and app_client != FATBIRD_CLIENT:
        result = await session.scalar(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.organizacao_id.asc().nulls_first(), UserRole.id)
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
