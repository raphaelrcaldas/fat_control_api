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
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.security.security import (
    PermissionDetailSchema,
    RoleDetailSchema,
    UserRoleSchema,
    UserWithRole,
)
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/roles')

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/', response_model=ApiResponse[list[RoleDetailSchema]])
async def list_roles(session: Session):
    stmt = (
        select(Roles)
        .options(
            joinedload(Roles.permissions)
            .joinedload(RolePermissions.permission)
            .joinedload(Permissions.resource)
        )
        .order_by(Roles.name)
    )
    result = await session.execute(stmt)
    roles = result.unique().scalars()

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
async def list_users_roles(session: Session):
    urs = await session.scalars(
        select(UserRole).options(joinedload(UserRole.user))
    )

    return success_response(data=list(urs.all()))


@router.get('/{role_id}', response_model=ApiResponse[RoleDetailSchema])
async def get_role_detail(role_id: int, session: Session):
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

    return success_response(message='Perfil cadastrado com sucesso')


@router.put('/users/', response_model=ApiResponse[None])
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

    return success_response(message='Perfil atualizado com sucesso')


@router.delete('/users/', response_model=ApiResponse[None])
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

    return success_response(message='Perfil deletado com sucesso')
