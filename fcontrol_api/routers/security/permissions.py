from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import Permissions, Resources
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.security import PermissionDetailSchema
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
