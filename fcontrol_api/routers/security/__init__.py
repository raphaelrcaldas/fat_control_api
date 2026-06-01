from fastapi import APIRouter, Depends

from fcontrol_api.routers.security import permissions, resources, roles
from fcontrol_api.security import require_admin, require_system_admin

router = APIRouter(
    prefix='/security',
    dependencies=[Depends(require_admin)],
)
# Definições globais de RBAC: somente admin de sistema.
router.include_router(
    permissions.router, dependencies=[Depends(require_system_admin)]
)
router.include_router(
    resources.router, dependencies=[Depends(require_system_admin)]
)
router.include_router(roles.router)
