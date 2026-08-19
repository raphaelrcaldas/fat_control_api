from fastapi import APIRouter, Depends

from fcontrol_api.routers.admin import diarias, funcoes, soldos
from fcontrol_api.security import require_system_admin

# Grupo admin de SISTEMA: control-plane acessível só ao admin de sistema
# (contexto Sistema, active_org NULL). O gate `require_system_admin` é
# declarado UMA vez aqui e vale para todos os routers-filhos.
router = APIRouter(
    prefix='/admin',
    dependencies=[Depends(require_system_admin)],
)
router.include_router(diarias.router)
router.include_router(funcoes.router)
router.include_router(soldos.router)
