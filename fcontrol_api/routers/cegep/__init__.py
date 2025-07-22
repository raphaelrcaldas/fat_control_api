from fastapi import APIRouter

import fcontrol_api.routers.cegep.financeiro as financeiro
import fcontrol_api.routers.cegep.missao as missao

router = APIRouter(prefix='/cegep')

router.include_router(missao.router)
router.include_router(financeiro.router)
