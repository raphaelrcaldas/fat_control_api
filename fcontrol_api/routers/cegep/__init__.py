from fastapi import APIRouter

from fcontrol_api.routers.cegep import comiss, financeiro, missao

router = APIRouter(prefix='/cegep')

router.include_router(missao.router)
router.include_router(financeiro.router)
router.include_router(comiss.router)
