from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.dados_bancarios import DadosBancarios
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.dados_bancarios import (
    DadosBancariosCreate,
    DadosBancariosPublic,
    DadosBancariosUpdate,
    DadosBancariosWithUser,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/dados-bancarios', tags=['CEGEP'])


@router.get('/', response_model=ApiResponse[list[DadosBancariosWithUser]])
async def get_dados_bancarios(
    session: Session,
    user_id: int = None,
    search: str = None,
):
    """Lista todos os dados bancários ou filtra por usuário/busca"""
    query = select(DadosBancarios).join(User)

    if user_id:
        query = query.where(DadosBancarios.user_id == user_id)

    if search:
        query = query.where(
            User.nome_guerra.ilike(f'%{search}%')
            | User.nome_completo.ilike(f'%{search}%')
        )

    result = await session.execute(query)
    dados = result.scalars().all()

    return success_response(data=list(dados))


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
