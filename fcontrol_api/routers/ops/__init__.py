from fastapi import APIRouter

from fcontrol_api.routers.ops import (
    aeronaves,
    escala,
    om,
    om_etiquetas,
    operacoes,
    quads,
    tripulantes,
)

router = APIRouter(prefix='/ops')
router.include_router(aeronaves.router)
router.include_router(escala.router)
# `/om/etiquetas` antes de `/om`: senão a rota `/om/{id}` do om.py casaria
# primeiro e o id viraria 422.
router.include_router(om_etiquetas.router)
router.include_router(om.router)
router.include_router(operacoes.router)
router.include_router(quads.router)
router.include_router(tripulantes.router)
