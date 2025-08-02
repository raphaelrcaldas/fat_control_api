from fastapi import APIRouter

import fcontrol_api.routers.cegep.comiss as comiss
import fcontrol_api.routers.cegep.financeiro as financeiro
import fcontrol_api.routers.cegep.missao as missao

router = APIRouter(prefix='/cegep')

router.include_router(missao.router)
router.include_router(financeiro.router)
router.include_router(comiss.router)
