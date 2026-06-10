from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.shared.aeronaves import ProjetoAnv, TenantProjeto
from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.schemas.projeto import ProjetoOut, TenantProjetoCreate
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.tenant import (
    TenantCreate,
    TenantOut,
    TenantUpdate,
)
from fcontrol_api.security import require_system_admin
from fcontrol_api.utils.responses import success_response

# Leitura (GET) liberada a qualquer autenticado — o client lista os tenants
# para gerência e seleção. Mutações exigem admin de sistema.
router = APIRouter(prefix='/tenants')

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/', response_model=ApiResponse[list[TenantOut]])
async def list_tenants(session: Session):
    tenants = await session.scalars(
        select(Tenant).order_by(Tenant.organizacao_id)
    )
    return success_response(
        data=[TenantOut.model_validate(t) for t in tenants]
    )


@router.post(
    '/',
    response_model=ApiResponse[TenantOut],
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_system_admin)],
)
async def create_tenant(body: TenantCreate, session: Session):
    org = await session.get(Organizacao, body.organizacao_id)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada no diretório',
        )

    existente = await session.get(Tenant, body.organizacao_id)
    if existente:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Organização já é um tenant da plataforma',
        )

    tenant = Tenant(organizacao_id=body.organizacao_id)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return success_response(
        data=TenantOut.model_validate(tenant),
        message='Tenant registrado com sucesso',
    )


@router.patch(
    '/{organizacao_id}',
    response_model=ApiResponse[TenantOut],
    dependencies=[Depends(require_system_admin)],
)
async def update_tenant(
    organizacao_id: str, body: TenantUpdate, session: Session
):
    tenant = await session.get(Tenant, organizacao_id)
    if not tenant:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tenant não encontrado',
        )

    tenant.active = body.active
    await session.commit()
    await session.refresh(tenant)
    return success_response(
        data=TenantOut.model_validate(tenant),
        message='Tenant atualizado com sucesso',
    )


@router.delete(
    '/{organizacao_id}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_system_admin)],
)
async def delete_tenant(organizacao_id: str, session: Session):
    tenant = await session.get(Tenant, organizacao_id)
    if not tenant:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tenant não encontrado',
        )

    # FK RESTRICT em user_roles: não dá para remover um tenant que ainda
    # possui vínculos de perfil. Antecipa um erro amigável.
    vinculo = await session.scalar(
        select(UserRole).where(UserRole.organizacao_id == organizacao_id)
    )
    if vinculo:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Tenant possui perfis vinculados. Remova os perfis '
                'antes de descadastrá-lo.'
            ),
        )

    await session.delete(tenant)
    await session.commit()
    return success_response(message='Tenant removido com sucesso')


@router.get(
    '/{organizacao_id}/projetos',
    response_model=ApiResponse[list[ProjetoOut]],
    dependencies=[Depends(require_system_admin)],
)
async def list_tenant_projetos(organizacao_id: str, session: Session):
    tenant = await session.get(Tenant, organizacao_id)
    if not tenant:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tenant não encontrado',
        )

    rows = await session.execute(
        select(ProjetoAnv.id_projeto, ProjetoAnv.modelo)
        .join(
            TenantProjeto, TenantProjeto.projeto == ProjetoAnv.id_projeto
        )
        .where(TenantProjeto.uae == organizacao_id)
        .order_by(ProjetoAnv.modelo)
    )
    return success_response(
        data=[
            ProjetoOut(id_projeto=r.id_projeto, modelo=r.modelo)
            for r in rows
        ]
    )


@router.post(
    '/{organizacao_id}/projetos',
    response_model=ApiResponse[ProjetoOut],
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_system_admin)],
)
async def add_tenant_projeto(
    organizacao_id: str, body: TenantProjetoCreate, session: Session
):
    tenant = await session.get(Tenant, organizacao_id)
    if not tenant:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tenant não encontrado',
        )

    projeto = await session.get(ProjetoAnv, body.projeto)
    if not projeto:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Projeto não encontrado',
        )

    existente = await session.scalar(
        select(TenantProjeto).where(
            TenantProjeto.uae == organizacao_id,
            TenantProjeto.projeto == body.projeto,
        )
    )
    if existente:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Projeto já associado a esta organização',
        )

    session.add(TenantProjeto(uae=organizacao_id, projeto=body.projeto))
    await session.commit()
    return success_response(
        data=ProjetoOut.model_validate(projeto),
        message='Projeto associado com sucesso',
    )


@router.delete(
    '/{organizacao_id}/projetos/{id_projeto}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_system_admin)],
)
async def remove_tenant_projeto(
    organizacao_id: str, id_projeto: str, session: Session
):
    vinculo = await session.scalar(
        select(TenantProjeto).where(
            TenantProjeto.uae == organizacao_id,
            TenantProjeto.projeto == id_projeto,
        )
    )
    if not vinculo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Associação não encontrada',
        )

    await session.delete(vinculo)
    await session.commit()
    return success_response(message='Projeto desassociado com sucesso')
