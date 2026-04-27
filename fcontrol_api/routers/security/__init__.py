from fastapi import APIRouter, Depends

from fcontrol_api.routers.security import permissions, resources, roles
from fcontrol_api.security import require_admin

router = APIRouter(
    prefix='/security',
    dependencies=[Depends(require_admin)],
)
router.include_router(permissions.router)
router.include_router(resources.router)
router.include_router(roles.router)
