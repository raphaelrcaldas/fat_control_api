from fastapi import APIRouter

from fcontrol_api.routers.cegep import (
    comiss,
    dados_bancarios,
    financeiro,
    missao,
    missao_etiquetas,
    orcamento,
    propostas,
    simulador,
)

router = APIRouter(prefix='/cegep')
router.include_router(comiss.router)
router.include_router(dados_bancarios.router)
router.include_router(financeiro.router)
# `/missoes/etiquetas` antes de `/missoes`: senão a rota `/missoes/{id}` do
# missao.py casaria primeiro e o id viraria 422.
router.include_router(missao_etiquetas.router)
router.include_router(simulador.router)
router.include_router(missao.router)
router.include_router(orcamento.router)
router.include_router(propostas.router)
