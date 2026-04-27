from fastapi import APIRouter

from fcontrol_api.routers.cegep import (
    comiss,
    dados_bancarios,
    diarias,
    financeiro,
    missao,
    orcamento,
    soldos,
)

router = APIRouter(prefix='/cegep')
router.include_router(comiss.router)
router.include_router(dados_bancarios.router)
router.include_router(diarias.router)
router.include_router(financeiro.router)
router.include_router(missao.router)
router.include_router(orcamento.router)
router.include_router(soldos.router)
