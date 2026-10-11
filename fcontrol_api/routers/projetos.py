from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.aeronaves import ProjetoAnv
from fcontrol_api.schemas.projeto import (
    ProjetoCreate,
    ProjetoOut,
    ProjetoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import require_system_admin
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

# Catálogo global de projetos/modelos de aeronave (control-plane).
# Gerenciado apenas pelo admin de sistema; os tenants consomem via
# associação (tenant_projetos) e o formulário de aeronaves.
router = APIRouter(
    prefix='/projetos',
    tags=['projetos'],
    dependencies=[Depends(require_system_admin)],
)


@router.get('/', response_model=ApiResponse[list[ProjetoOut]])
async def list_projetos(session: Session):
    projetos = await session.scalars(
        select(ProjetoAnv).order_by(ProjetoAnv.modelo)
    )
    return success_response(
        data=[ProjetoOut.model_validate(p) for p in projetos]
    )


@router.post(
    '/',
    response_model=ApiResponse[ProjetoOut],
    status_code=HTTPStatus.CREATED,
)
async def create_projeto(body: ProjetoCreate, session: Session):
    existente = await session.get(ProjetoAnv, body.id_projeto)
    if existente:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe um projeto com este identificador',
        )

    projeto = ProjetoAnv(id_projeto=body.id_projeto, modelo=body.modelo)
    session.add(projeto)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe um projeto com este modelo',
        )
    await session.refresh(projeto)
    return success_response(
        data=ProjetoOut.model_validate(projeto),
        message='Projeto cadastrado com sucesso',
    )


@router.put(
    '/{id_projeto}',
    response_model=ApiResponse[ProjetoOut],
)
async def update_projeto(
    id_projeto: str, body: ProjetoUpdate, session: Session
):
    # O id é gravado em caixa alta; `c1` na URL acha o `C1`.
    projeto = await session.get(ProjetoAnv, id_projeto.strip().upper())
    if not projeto:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Projeto não encontrado',
        )

    projeto.modelo = body.modelo
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe um projeto com este modelo',
        )
    await session.refresh(projeto)
    return success_response(
        data=ProjetoOut.model_validate(projeto),
        message='Projeto atualizado com sucesso',
    )


@router.delete(
    '/{id_projeto}',
    response_model=ApiResponse[None],
)
async def delete_projeto(id_projeto: str, session: Session):
    projeto = await session.get(ProjetoAnv, id_projeto.strip().upper())
    if not projeto:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Projeto não encontrado',
        )

    # Aeronaves (`aeronaves.projeto`), tripulantes (`tripulantes.proj`, pelo
    # modelo) e organizações (`tenant_projetos`) seguram o projeto por FK: o
    # banco recusa e a rota traduz o IntegrityError em 409.
    await session.delete(projeto)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Projeto em uso por aeronaves, tripulantes ou organizações. '
                'Remova os vínculos antes de excluí-lo.'
            ),
        )
    return success_response(message='Projeto removido com sucesso')
