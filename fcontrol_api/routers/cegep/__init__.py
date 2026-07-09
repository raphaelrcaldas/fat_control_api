from fastapi import APIRouter

from fcontrol_api.routers.cegep import (
    comiss,
    dados_bancarios,
    financeiro,
    missao,
    orcamento,
)

router = APIRouter(prefix='/cegep')
router.include_router(comiss.router)
router.include_router(dados_bancarios.router)
router.include_router(financeiro.router)
router.include_router(missao.router)
router.include_router(orcamento.router)
