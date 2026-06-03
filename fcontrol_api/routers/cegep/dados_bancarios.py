from datetime import date
from decimal import Decimal
from http import HTTPStatus
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.dados_bancarios import (
    DadosBancariosBulkDelete,
    DadosBancariosBulkDeleteResponse,
    DadosBancariosCreate,
    DadosBancariosPublic,
    DadosBancariosUpdate,
    DadosBancariosWithUser,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.services.portal_transparencia import buscar_remuneracao
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/dados-bancarios', tags=['CEGEP'])


class SyncRemuneracaoRequest(BaseModel):
    user_id: int = Field(description='ID do militar a consultar')
    mes_ano: date = Field(
        description='Mes de referencia (qualquer dia do mes alvo)'
    )


class SyncRemuneracaoResponse(BaseModel):
    cpf: str
    mes_ano: date
    remuneracao_bruta: Optional[Decimal] = None
    remuneracao_liquida: Optional[Decimal] = None


@router.get('/', response_model=ApiResponse[list[DadosBancariosWithUser]])
async def get_dados_bancarios(
    session: Session,
    user_id: int = None,
    search: str = None,
):
    """Lista dados bancários de usuários ativos (filtra por usuário/busca)"""
    query = select(DadosBancarios).join(User).where(User.active.is_(True))

    if user_id:
        query = query.where(DadosBancarios.user_id == user_id)

    if search:
        query = query.where(
            User.nome_guerra.ilike(f'%{search}%')
            | User.nome_completo.ilike(f'%{search}%')
        )

    query = query.order_by(DadosBancarios.id)

    result = await session.execute(query)
    dados = result.scalars().all()

    return success_response(data=list(dados))


@router.get(
    '/orfaos',
    response_model=ApiResponse[list[DadosBancariosWithUser]],
)
async def get_dados_bancarios_orfaos(
    session: Session,
):
    """Lista dados bancários cujo usuário está desativado (órfãos)"""
    query = (
        select(DadosBancarios)
        .join(User)
        .where(User.active.is_(False))
        .order_by(DadosBancarios.id)
    )

    result = await session.execute(query)
    dados = result.scalars().all()

    return success_response(data=list(dados))


@router.delete(
    '/orfaos',
    response_model=ApiResponse[DadosBancariosBulkDeleteResponse],
)
async def delete_dados_bancarios_orfaos(
    session: Session,
    payload: DadosBancariosBulkDelete,
):
    """Remove dados bancários órfãos selecionados.

    Por segurança, deleta apenas a interseção entre os ids recebidos e
    os registros realmente órfãos (usuário desativado), recomputando o
    conjunto órfão dentro do handler. Nunca remove dados de usuário ativo.
    """
    ids_query = (
        select(DadosBancarios.id)
        .join(User)
        .where(
            DadosBancarios.id.in_(payload.ids),
            User.active.is_(False),
        )
    )

    result = await session.execute(ids_query)
    orfaos_ids = result.scalars().all()

    if orfaos_ids:
        await session.execute(
            delete(DadosBancarios).where(DadosBancarios.id.in_(orfaos_ids))
        )
        await session.commit()

    deleted = len(orfaos_ids)

    return success_response(
        data=DadosBancariosBulkDeleteResponse(deleted=deleted),
        message=f'{deleted} registros removidos com sucesso',
    )


@router.get('/{dados_id}', response_model=ApiResponse[DadosBancariosWithUser])
async def get_dados_bancarios_by_id(
    dados_id: int,
    session: Session,
):
    """Busca dados bancários por ID"""
    dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.id == dados_id)
    )

    if not dados:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Dados bancários não encontrados',
        )

    return success_response(data=dados)


@router.get(
    '/user/{user_id}',
    response_model=ApiResponse[DadosBancariosPublic],
)
async def get_dados_bancarios_by_user(
    user_id: int,
    session: Session,
):
    """Busca dados bancários por ID do usuário"""
    dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.user_id == user_id)
    )

    if not dados:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Dados bancários não encontrados para este usuário',
        )

    return success_response(data=dados)


@router.post(
    '/sync-remuneracao',
    response_model=ApiResponse[SyncRemuneracaoResponse],
)
async def sync_remuneracao_portal(
    session: Session,
    payload: SyncRemuneracaoRequest,
):
    """Consulta o Portal da Transparencia para um usuario+mes.

    Funciona em modo create (sem registro ainda) e edit. NAO persiste
    no banco — o frontend decide se preenche o formulario e salva.
    """
    user = await session.scalar(
        select(User).where(User.id == payload.user_id)
    )
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )
    if not user.cpf:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='Usuário sem CPF cadastrado',
        )

    resultado = await buscar_remuneracao(user.cpf, payload.mes_ano)

    return success_response(
        data=SyncRemuneracaoResponse(
            cpf=user.cpf,
            mes_ano=resultado['mes_ano'],
            remuneracao_bruta=resultado['remuneracao_bruta'],
            remuneracao_liquida=resultado['remuneracao_liquida'],
        ),
        message='Remuneração consultada com sucesso',
    )


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[DadosBancariosPublic],
)
async def create_dados_bancarios(
    session: Session,
    dados: DadosBancariosCreate,
):
    """Cria novos dados bancários para um usuário"""
    # Verifica se o usuário existe
    user = await session.scalar(select(User).where(User.id == dados.user_id))
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )

    # Verifica se já existem dados bancários para este usuário
    dados_existentes = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.user_id == dados.user_id)
    )
    if dados_existentes:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Já existem dados bancários cadastrados para este usuário',
        )

    dados_dict = dados.model_dump()
    new_dados = DadosBancarios(**dados_dict)

    session.add(new_dados)
    await session.commit()
    await session.refresh(new_dados)

    return success_response(
        data=DadosBancariosPublic.model_validate(new_dados),
        message='Dados bancários criados com sucesso',
    )


@router.put('/{dados_id}', response_model=ApiResponse[None])
async def update_dados_bancarios(
    dados_id: int,
    session: Session,
    dados: DadosBancariosUpdate,
):
    """Atualiza dados bancários existentes"""
    db_dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.id == dados_id)
    )

    if not db_dados:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Dados bancários não encontrados',
        )

    for key, value in dados.model_dump(exclude_unset=True).items():
        setattr(db_dados, key, value)

    await session.commit()
    await session.refresh(db_dados)

    return success_response(message='Dados bancários atualizados com sucesso')


@router.delete('/{dados_id}', response_model=ApiResponse[None])
async def delete_dados_bancarios(
    dados_id: int,
    session: Session,
):
    """Deleta dados bancários"""
    db_dados = await session.scalar(
        select(DadosBancarios).where(DadosBancarios.id == dados_id)
    )

    if not db_dados:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Dados bancários não encontrados',
        )

    await session.delete(db_dados)
    await session.commit()

    return success_response(message='Dados bancários deletados com sucesso')
