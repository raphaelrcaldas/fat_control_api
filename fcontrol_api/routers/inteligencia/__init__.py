from fastapi import APIRouter

from fcontrol_api.routers.inteligencia import passaportes

router = APIRouter(prefix='/inteligencia')
router.include_router(passaportes.router)
