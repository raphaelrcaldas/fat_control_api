from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tenant import Tenant
from fcontrol_api.schemas.organizacao import (
    OrganizacaoCreate,
    OrganizacaoOut,
    OrganizacaoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import require_system_admin
from fcontrol_api.utils.responses import success_response

# Leitura (GET) liberada a qualquer autenticado — o client precisa do
# diretório de orgs (siglas/nomes). Mutações exigem admin de sistema.
router = APIRouter(prefix='/organizacoes')

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get('/', response_model=ApiResponse[list[OrganizacaoOut]])
async def list_organizacoes(session: Session):
    orgs = await session.scalars(
        select(Organizacao).order_by(Organizacao.sigla)
    )
    return success_response(
        data=[OrganizacaoOut.model_validate(o) for o in orgs]
    )


@router.get('/{sigla}', response_model=ApiResponse[OrganizacaoOut])
async def get_organizacao(sigla: str, session: Session):
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )
    return success_response(data=OrganizacaoOut.model_validate(org))


@router.post(
    '/',
    response_model=ApiResponse[OrganizacaoOut],
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_system_admin)],
)
async def create_organizacao(body: OrganizacaoCreate, session: Session):
    org = Organizacao(
        sigla=body.sigla,
        sigla_2=body.sigla_2,
        sigla_3=body.sigla_3,
        nome=body.nome,
        alias=body.alias,
    )
    session.add(org)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe uma organização com uma dessas siglas',
        )
    await session.refresh(org)
    return success_response(
        data=OrganizacaoOut.model_validate(org),
        message='Organização cadastrada com sucesso',
    )


@router.put(
    '/{sigla}',
    response_model=ApiResponse[OrganizacaoOut],
    dependencies=[Depends(require_system_admin)],
)
async def update_organizacao(
    sigla: str, body: OrganizacaoUpdate, session: Session
):
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )

    dados = body.model_dump(exclude_unset=True)
    # A sigla de um tenant não muda: `user_roles` a referencia sem cascade
    # (o banco recusava e a rota caía no 409 de sigla duplicada), e o
    # `active_org` dos tokens emitidos e os brasões usam a sigla antiga.
    if dados.get('sigla', sigla) != sigla and await session.get(Tenant, sigla):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'A sigla de um tenant da plataforma não pode ser alterada.'
            ),
        )

    for field, value in dados.items():
        setattr(org, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Já existe uma organização com uma dessas siglas',
        )
    await session.refresh(org)
    return success_response(
        data=OrganizacaoOut.model_validate(org),
        message='Organização atualizada com sucesso',
    )


@router.delete(
    '/{sigla}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_system_admin)],
)
async def delete_organizacao(sigla: str, session: Session):
    org = await session.get(Organizacao, sigla)
    if not org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Organização não encontrada',
        )

    # FK RESTRICT em tenants.organizacao_id: não dá para remover do
    # diretório uma org que é cliente da plataforma. Antecipa erro amigável.
    tenant = await session.get(Tenant, sigla)
    if tenant:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Organização é um tenant da plataforma. Descadastre o '
                'tenant antes de removê-la do diretório.'
            ),
        )

    # Usuários, feedbacks e notificações também seguram a org por FK
    # RESTRICT: o banco recusa e a rota traduz em 409.
    await session.delete(org)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Organização em uso por usuários ou outros registros. '
                'Remova os vínculos antes de excluí-la.'
            ),
        )
    return success_response(message='Organização removida com sucesso')
