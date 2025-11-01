from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.resources import Roles, UserRole
from fcontrol_api.schemas.security import (
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
async def api_list_roles(session: Session):
    q = select(Roles)
    result = await session.scalars(q)

    return result.all()


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
