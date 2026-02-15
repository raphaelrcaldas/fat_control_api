from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import Permissions, Resources
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.security.security import (
    ResourceCreate,
    ResourceSchema,
    ResourceUpdate,
)
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/resources')

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/', response_model=ApiResponse[list[ResourceSchema]])
async def list_resources(session: Session):
    stmt = select(Resources).order_by(Resources.name)
    resources = await session.scalars(stmt)
    return success_response(data=list(resources))


@router.post(
    '/',
    response_model=ApiResponse[ResourceSchema],
    status_code=HTTPStatus.CREATED,
)
async def create_resource(resource_data: ResourceCreate, session: Session):
    resource = Resources(
        name=resource_data.name, description=resource_data.description
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return success_response(data=resource)


@router.put('/{resource_id}', response_model=ApiResponse[ResourceSchema])
async def update_resource(
    resource_id: int, resource_data: ResourceUpdate, session: Session
):
    stmt = select(Resources).where(Resources.id == resource_id)
    result = await session.execute(stmt)
    resource = result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Recurso nao encontrado'
        )

    # Update only non-None fields
    if resource_data.name is not None:
        resource.name = resource_data.name
    if resource_data.description is not None:
        resource.description = resource_data.description

    await session.commit()
    await session.refresh(resource)
    return success_response(data=resource)


@router.delete('/{resource_id}', response_model=ApiResponse[None])
async def delete_resource(resource_id: int, session: Session):
    stmt = select(Resources).where(Resources.id == resource_id)
    result = await session.execute(stmt)
    resource = result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Recurso nao encontrado'
        )

    # Check for linked permissions
    perm_stmt = select(Permissions).where(
        Permissions.resource_id == resource_id
    )
    perm_result = await session.execute(perm_stmt)
    linked_permissions = perm_result.first()

    if linked_permissions:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Recurso possui permissoes vinculadas',
        )

    await session.delete(resource)
    await session.commit()
    return success_response(data=None)
