from fastapi import APIRouter

from fcontrol_api.routers.ops import aeronaves, funcoes, om, quads, tripulantes

router = APIRouter(prefix='/ops')
router.include_router(aeronaves.router)
router.include_router(funcoes.router)
router.include_router(om.router)
router.include_router(quads.router)
router.include_router(tripulantes.router)
