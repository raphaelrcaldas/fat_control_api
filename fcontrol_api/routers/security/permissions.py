from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.security.security import (
    PermissionCreate,
    PermissionDetailSchema,
    PermissionUpdate,
)
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/permissions')

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/', response_model=ApiResponse[list[PermissionDetailSchema]])
async def list_permissions(session: Session, resource_name: str | None = None):
    stmt = (
        select(Permissions)
        .options(joinedload(Permissions.resource))
        .order_by(Permissions.resource_id, Permissions.name)
    )

    if resource_name:
        stmt = stmt.join(Resources).where(Resources.name == resource_name)

    permissions = await session.scalars(stmt)

    return success_response(
        data=[
            PermissionDetailSchema(
                id=p.id,
                resource=p.resource.name,
                action=p.name,
                description=p.description,
            )
            for p in permissions
        ]
    )


@router.post(
    '/',
    response_model=ApiResponse[PermissionDetailSchema],
    status_code=HTTPStatus.CREATED,
)
async def create_permission(
    permission_data: PermissionCreate,
    session: Session,
):
    resource = await session.get(Resources, permission_data.resource_id)
    if not resource:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Recurso não encontrado',
        )

    new_permission = Permissions(
        resource_id=permission_data.resource_id,
        name=permission_data.name,
        description=permission_data.description,
    )

    session.add(new_permission)
    await session.commit()
    await session.refresh(new_permission, ['resource'])

    return success_response(
        data=PermissionDetailSchema(
            id=new_permission.id,
            resource=new_permission.resource.name,
            action=new_permission.name,
            description=new_permission.description,
        )
    )


@router.put(
    '/{permission_id}',
    response_model=ApiResponse[PermissionDetailSchema],
)
async def update_permission(
    permission_id: int,
    permission_data: PermissionUpdate,
    session: Session,
):
    permission = await session.get(Permissions, permission_id)
    if not permission:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Permissão não encontrada',
        )

    update_fields = permission_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(permission, field, value)

    await session.commit()
    await session.refresh(permission, ['resource'])

    return success_response(
        data=PermissionDetailSchema(
            id=permission.id,
            resource=permission.resource.name,
            action=permission.name,
            description=permission.description,
        )
    )


@router.delete(
    '/{permission_id}',
    response_model=ApiResponse[PermissionDetailSchema],
)
async def delete_permission(
    permission_id: int,
    session: Session,
):
    stmt = (
        select(Permissions)
        .options(joinedload(Permissions.resource))
        .where(Permissions.id == permission_id)
    )
    result = await session.execute(stmt)
    permission = result.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Permissão não encontrada',
        )

    linked_roles = await session.execute(
        select(RolePermissions).where(
            RolePermissions.permission_id == permission_id
        )
    )
    if linked_roles.scalars().first():
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Permissão possui roles vinculados',
        )

    permission_detail = PermissionDetailSchema(
        id=permission.id,
        resource=permission.resource.name,
        action=permission.name,
        description=permission.description,
    )

    await session.delete(permission)
    await session.commit()

    return success_response(data=permission_detail)
