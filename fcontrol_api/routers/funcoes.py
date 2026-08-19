"""Catálogo de funções de tripulante (leitura).

Leitura sem gate além do token: rotular 'pil' como "Piloto" é necessário em
praticamente toda tela que mostra tripulante — escala, quadros, etapas,
indisponibilidades. O que é escopado por org é o conjunto **operado**, que
sai em `GET /config/funcoes`; a manutenção do catálogo mora em
`/admin/funcoes`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.funcoes import Funcao
from fcontrol_api.schemas.funcoes import FuncaoOut
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/funcoes', tags=['Funcoes'])


@router.get('/', response_model=ApiResponse[list[FuncaoOut]])
async def list_funcoes(
    session: Session,
    incluir_inativas: Annotated[bool, Query()] = False,
):
    """Catálogo global de funções, com as posições a bordo de cada uma."""
    query = select(Funcao).order_by(Funcao.ordem, Funcao.cod)
    if not incluir_inativas:
        query = query.where(Funcao.active.is_(True))

    funcoes = (await session.scalars(query)).all()

    return success_response(
        data=[FuncaoOut.model_validate(f) for f in funcoes]
    )
