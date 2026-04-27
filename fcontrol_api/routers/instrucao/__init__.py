from fastapi import APIRouter

from fcontrol_api.routers.instrucao import idiomas

router = APIRouter(prefix='/instrucao')
router.include_router(idiomas.router)
