from fastapi import APIRouter

from fcontrol_api.routers.seg_voo import crm

router = APIRouter(prefix='/seg-voo')
router.include_router(crm.router)
