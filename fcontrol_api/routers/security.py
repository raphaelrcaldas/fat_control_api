from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.schemas.security import (
    PermissionDetailSchema,
    ResourceSchema,
    RoleDetailSchema,
    RoleSchema,
    UserRoleSchema,
    UserWithRole,
)
from fcontrol_api.security import require_admin

router = APIRouter(
    prefix='/security',
    tags=['security'],
    dependencies=[Depends(require_admin)],
)

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/roles', response_model=list[RoleSchema])
async def list_roles(session: Session, _: User = Depends(require_admin)):
    stmt = select(Roles).order_by(Roles.name)
    roles = await session.scalars(stmt)

    return list(roles)


@router.get('/roles/{role_id}', response_model=RoleDetailSchema)
async def get_role_detail(
    role_id: int, session: Session, _: User = Depends(require_admin)
):
    stmt = (
        select(Roles)
        .where(Roles.id == role_id)
        .options(
            joinedload(Roles.permissions)
            .joinedload(RolePermissions.permission)
            .joinedload(Permissions.resource)
        )
    )

    role = await session.scalar(stmt)

    if not role:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Role não encontrada'
        )

    return RoleDetailSchema(
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


@router.get('/roles/users', response_model=list[UserWithRole])
async def list_users_roles(session: Session):
    urs = await session.scalars(
        select(UserRole).options(joinedload(UserRole.user))
    )

    return urs.all()


@router.post('/roles/users')
async def add_user_role(new_role: UserRoleSchema, session: Session):
    user = await session.scalar(
        select(User).where(User.id == new_role.user_id)
    )
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )

    ur = UserRole(user_id=new_role.user_id, role_id=new_role.role_id)

    session.add(ur)
    await session.commit()

    return {'detail': 'Perfil cadastrado com sucesso'}


@router.put('/roles/users')
async def update_user_role(role_patch: UserRoleSchema, session: Session):
    user_reg = await session.scalar(
        select(UserRole).where(UserRole.user_id == role_patch.user_id)
    )
    if not user_reg:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não tem perfil cadastrado',
        )

    user_reg.role_id = role_patch.role_id

    await session.commit()

    return {'detail': 'Perfil atualizado com sucesso'}


@router.delete('/roles/users')
async def delete_user_role(role_body: UserRoleSchema, session: Session):
    user_reg = await session.scalar(
        select(UserRole).where(UserRole.user_id == role_body.user_id)
    )
    if not user_reg:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não tem perfil cadastrado',
        )

    if not (role_body.role_id == user_reg.role_id):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Roles não conferem',
        )

    await session.delete(user_reg)
    await session.commit()

    return {'detail': 'Perfil deletado com sucesso'}


@router.get('/resources', response_model=list[ResourceSchema])
async def list_resources(session: Session, _: User = Depends(require_admin)):
    stmt = select(Resources).order_by(Resources.name)
    resources = await session.scalars(stmt)
    return list(resources)


@router.get('/permissions', response_model=list[PermissionDetailSchema])
async def list_permissions(
    session: Session,
    resource_name: str | None = None,  # Filtro opcional
    _: User = Depends(require_admin),
):
    stmt = (
        select(Permissions)
        .options(joinedload(Permissions.resource))
        .order_by(Permissions.resource_id, Permissions.name)
    )

    if resource_name:
        stmt = stmt.join(Resources).where(Resources.name == resource_name)

    permissions = await session.scalars(stmt)

    return [
        PermissionDetailSchema(
            id=p.id,
            resource=p.resource.name,
            action=p.name,
            description=p.description,
        )
        for p in permissions
    ]
