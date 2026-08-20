from fastapi import APIRouter

from fcontrol_api.routers.instrucao import cartoes, paops, subprogramas

router = APIRouter(prefix='/instrucao')
router.include_router(cartoes.router)
router.include_router(subprogramas.router)
router.include_router(paops.router)
