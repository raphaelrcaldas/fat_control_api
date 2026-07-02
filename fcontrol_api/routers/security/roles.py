from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import (
    Permissions,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.security.security import (
    PermissionDetailSchema,
    RoleDetailSchema,
    RolePermissionAction,
    UserRoleSchema,
    UserWithRole,
)
from fcontrol_api.security import (
    AdminScope,
    get_admin_scope,
    require_system_admin,
)
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/roles')

Session = Annotated[AsyncSession, Depends(get_session)]
Scope = Annotated[AdminScope, Depends(get_admin_scope)]

# Apenas a role 'admin' pode existir sem organização (escopo de sistema).
# As demais roles são sempre vinculadas a uma unidade.
SYSTEM_SCOPED_ROLE = 'admin'


def _ensure_org_in_scope(
    scope: AdminScope, organizacao_id: str | None
) -> None:
    """Admin de unidade só opera vínculos da própria org ativa."""
    if not scope.is_system and organizacao_id != scope.active_org:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Operação fora do escopo da sua organização',
        )


async def _validate_role_scope(
    role_id: int, organizacao_id: str | None, session: AsyncSession
) -> Roles:
    """Valida a role e a regra de escopo (NULL só é permitido p/ admin)."""
    role = await session.get(Roles, role_id)
    if not role:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Perfil não encontrado',
        )

    if organizacao_id is None and role.name != SYSTEM_SCOPED_ROLE:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Apenas o perfil de administrador pode ser do sistema '
                '(sem unidade). Selecione uma unidade para este perfil.'
            ),
        )

    return role


@router.get('/', response_model=ApiResponse[list[RoleDetailSchema]])
async def list_roles(session: Session):
    stmt = (
        select(Roles)
        .options(
            selectinload(Roles.permissions)
            .selectinload(RolePermissions.permission)
            .selectinload(Permissions.resource)
        )
        .order_by(Roles.name)
    )
    result = await session.execute(stmt)
    roles = result.scalars()

    return success_response(
        data=[
            RoleDetailSchema(
                id=role.id,
                name=role.name,
                description=role.description,
                permissions=[
                    PermissionDetailSchema(
                        id=rp.permission.id,
                        resource=rp.permission.resource.name,
                        action=rp.permission.name,
                        description=rp.permission.description,
                    )
                    for rp in role.permissions
                ],
            )
            for role in roles
        ]
    )


@router.get('/users/', response_model=ApiResponse[list[UserWithRole]])
async def list_users_roles(session: Session, scope: Scope):
    # A org ativa é sempre a lente: cada contexto mostra só os vínculos
    # daquela org. "Sistema" (NULL) mostra apenas os vínculos de sistema.
    stmt = (
        select(UserRole)
        .where(UserRole.organizacao_id.is_not_distinct_from(scope.active_org))
        .options(joinedload(UserRole.user))
    )

    urs = await session.scalars(stmt)

    return success_response(data=list(urs.all()))


@router.get('/{role_id}', response_model=ApiResponse[RoleDetailSchema])
async def get_role_detail(role_id: int, session: Session):
    stmt = (
        select(Roles)
        .where(Roles.id == role_id)
        .options(
            selectinload(Roles.permissions)
            .selectinload(RolePermissions.permission)
            .selectinload(Permissions.resource)
        )
    )

    role = await session.scalar(stmt)

    if not role:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Perfil não encontrado'
        )

    return success_response(
        data=RoleDetailSchema(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=[
                PermissionDetailSchema(
                    id=rp.permission.id,
                    resource=rp.permission.resource.name,
                    action=rp.permission.name,
                    description=rp.permission.description,
                )
                for rp in role.permissions
            ],
        )
    )


@router.post('/users/', response_model=ApiResponse[None])
async def add_user_role(
    new_role: UserRoleSchema, session: Session, scope: Scope
):
    _ensure_org_in_scope(scope, new_role.organizacao_id)

    user = await session.scalar(
        select(User).where(User.id == new_role.user_id)
    )
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )

    if new_role.organizacao_id is not None:
        tenant = await session.get(Tenant, new_role.organizacao_id)
        if not tenant:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail='Organização não é um tenant da plataforma',
            )

    await _validate_role_scope(
        new_role.role_id, new_role.organizacao_id, session
    )

    # 1 role por (usuário, org): impede vínculo duplicado na mesma org
    existente = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == new_role.user_id,
            UserRole.organizacao_id.is_not_distinct_from(
                new_role.organizacao_id
            ),
        )
    )
    if existente:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Usuário já possui um perfil nessa organização',
        )

    ur = UserRole(
        user_id=new_role.user_id,
        role_id=new_role.role_id,
        organizacao_id=new_role.organizacao_id,
    )

    session.add(ur)
    await session.commit()

    return success_response(message='Perfil cadastrado com sucesso')


@router.put('/users/', response_model=ApiResponse[None])
async def update_user_role(
    role_patch: UserRoleSchema, session: Session, scope: Scope
):
    _ensure_org_in_scope(scope, role_patch.organizacao_id)

    # Localiza o vínculo do usuário na org informada (NULL = sistema)
    user_reg = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == role_patch.user_id,
            UserRole.organizacao_id.is_not_distinct_from(
                role_patch.organizacao_id
            ),
        )
    )
    if not user_reg:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não tem perfil cadastrado nessa organização',
        )

    await _validate_role_scope(
        role_patch.role_id, role_patch.organizacao_id, session
    )

    user_reg.role_id = role_patch.role_id

    await session.commit()

    return success_response(message='Perfil atualizado com sucesso')


@router.delete('/users/', response_model=ApiResponse[None])
async def delete_user_role(
    role_body: UserRoleSchema, session: Session, scope: Scope
):
    _ensure_org_in_scope(scope, role_body.organizacao_id)

    if role_body.user_id == scope.user.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você não pode remover o próprio acesso',
        )

    user_reg = await session.scalar(
        select(UserRole).where(
            UserRole.user_id == role_body.user_id,
            UserRole.organizacao_id.is_not_distinct_from(
                role_body.organizacao_id
            ),
        )
    )
    if not user_reg:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não tem perfil cadastrado nessa organização',
        )

    if not (role_body.role_id == user_reg.role_id):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Roles não conferem',
        )

    await session.delete(user_reg)
    await session.commit()

    return success_response(message='Perfil deletado com sucesso')


@router.post(
    '/{role_id}/permissions/',
    response_model=ApiResponse[None],
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_system_admin)],
)
async def add_permission_to_role(
    role_id: int, body: RolePermissionAction, session: Session
):
    role = await session.get(Roles, role_id)
    if not role:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Perfil não encontrado',
        )

    permission = await session.get(Permissions, body.permission_id)
    if not permission:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Permissão não encontrada',
        )

    existing = await session.scalar(
        select(RolePermissions).where(
            (RolePermissions.role_id == role_id)
            & (RolePermissions.permission_id == body.permission_id)
        )
    )
    if existing:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Perfil já possui esta permissão',
        )

    rp = RolePermissions(
        role_id=role_id,
        permission_id=body.permission_id,
    )
    session.add(rp)
    await session.commit()

    return success_response(
        message='Permissão adicionada ao perfil com sucesso'
    )


@router.delete(
    '/{role_id}/permissions/{permission_id}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_system_admin)],
)
async def remove_permission_from_role(
    role_id: int, permission_id: int, session: Session
):
    result = await session.scalar(
        select(RolePermissions).where(
            (RolePermissions.role_id == role_id)
            & (RolePermissions.permission_id == permission_id)
        )
    )

    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Perfil não possui esta permissão',
        )

    await session.delete(result)
    await session.commit()

    return success_response(message='Permissão removida do perfil com sucesso')
