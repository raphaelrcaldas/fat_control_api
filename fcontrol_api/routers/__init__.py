from fastapi import APIRouter

from fcontrol_api.routers import (
    admin_cleanup,
    aeromedica,
    auth,
    cegep,
    cities,
    estatistica,
    indisp,
    instrucao,
    inteligencia,
    logs,
    nav,
    ops,
    organizacoes,
    postos,
    projetos,
    security,
    seg_voo,
    storage,
    tenants,
    users,
)

router = APIRouter()
router.include_router(admin_cleanup.router)
router.include_router(aeromedica.router)
router.include_router(auth.router)
router.include_router(cegep.router)
router.include_router(cities.router)
router.include_router(estatistica.router)
router.include_router(indisp.router)
router.include_router(instrucao.router)
router.include_router(inteligencia.router)
router.include_router(logs.router)
router.include_router(nav.router)
router.include_router(ops.router)
router.include_router(organizacoes.router)
router.include_router(postos.router)
router.include_router(projetos.router)
router.include_router(security.router)
router.include_router(seg_voo.router)
router.include_router(storage.router)
router.include_router(tenants.router)
router.include_router(users.router)
