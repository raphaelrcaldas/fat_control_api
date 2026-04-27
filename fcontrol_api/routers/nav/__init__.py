from fastapi import APIRouter

from fcontrol_api.routers.nav import aerodromos

router = APIRouter(prefix='/nav')
router.include_router(aerodromos.router)
