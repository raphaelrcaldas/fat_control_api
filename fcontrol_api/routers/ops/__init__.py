from fastapi import APIRouter

from . import funcoes, quads, tripulantes

router = APIRouter(prefix='/ops')

router.include_router(funcoes.router)
router.include_router(quads.router)
router.include_router(tripulantes.router)