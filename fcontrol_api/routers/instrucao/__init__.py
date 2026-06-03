from fastapi import APIRouter

from fcontrol_api.routers.instrucao import cartoes

router = APIRouter(prefix='/instrucao')
router.include_router(cartoes.router)
