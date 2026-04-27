from fastapi import APIRouter

from fcontrol_api.routers.aeromedica import atas, cartoes

router = APIRouter(prefix='/aeromedica')
router.include_router(atas.router)
router.include_router(cartoes.router)
