from fastapi import APIRouter

from fcontrol_api.routers.estatistica import (
    esf_aer,
    etapas,
    horas_anv,
    missao,
    sebo,
    tipo_missao,
)

router = APIRouter(prefix='/estatistica')
router.include_router(esf_aer.router)
router.include_router(etapas.router)
router.include_router(horas_anv.router)
router.include_router(missao.router)
router.include_router(sebo.router)
router.include_router(tipo_missao.router)
