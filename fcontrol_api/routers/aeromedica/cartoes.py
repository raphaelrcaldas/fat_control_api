from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.aeromedica.cartoes import (
    CartaoSaudeCreate,
    CartaoSaudePublic,
    CartaoSaudeUpdate,
    CartaoSaudeWithUser,
    UserCartaoSaude,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/cartoes-saude', tags=['Aeromedica'])


@router.get(
    '/',
    response_model=ApiResponse[list[UserCartaoSaude]],
)
async def get_cartoes_saude(
    session: Session,
    search: str | None = None,
    p_g: str | None = None,
    funcao: str | None = None,
    tripulante: bool | None = None,
):
    """Lista usuarios com seus cartoes de saude."""
    cemal_tem_ata = (
        exists(
            select(AtaInspecao.id).where(
                AtaInspecao.user_id == User.id,
                AtaInspecao.validade_inspsau == CartaoSaude.cemal,
            )
        )
        .correlate(User, CartaoSaude)
        .label('cemal_tem_ata')
    )

    total_atas = (
        select(func.count(AtaInspecao.id))
        .where(AtaInspecao.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
        .label('total_atas')
    )

    query = (
        select(
            User,
            CartaoSaude,
            Tripulante.id,
            cemal_tem_ata,
            total_atas,
        )
        .join(PostoGrad)
        .outerjoin(
            Tripulante,
            Tripulante.user_id == User.id,
        )
        .outerjoin(
            CartaoSaude,
            CartaoSaude.user_id == User.id,
        )
        .where(User.active.is_(True))
    )

    # Filtro base: tripulantes + nao-tripulantes do 11gt
    if tripulante is True:
        query = query.where(Tripulante.id.isnot(None))
    elif tripulante is False:
        query = query.where(
            Tripulante.id.is_(None),
            User.unidade == '11gt',
        )
    else:
        query = query.where(
            or_(
                Tripulante.id.isnot(None),
                User.unidade == '11gt',
            )
        )

    if search:
        safe = (
            search
            .replace('\\', '\\\\')
            .replace('%', '\\%')
            .replace('_', '\\_')
        )
        pattern = f'%{safe}%'
        query = query.where(
            User.nome_guerra.ilike(pattern) | User.nome_completo.ilike(pattern)
        )

    if p_g:
        pgs = [p.strip() for p in p_g.split(',')]
        query = query.where(User.p_g.in_(pgs))

    if funcao:
        funcs = [f.strip() for f in funcao.split(',')]
        query = (
            query
            .where(Tripulante.id.isnot(None))
            .where(Funcao.func.in_(funcs))
            .join(
                Funcao,
                Funcao.trip_id == Tripulante.id,
            )
        )

    query = query.order_by(
        PostoGrad.ant.asc(),
        User.ult_promo.asc(),
        User.ant_rel.asc(),
        User.id,
    )

    result = await session.execute(query)
    rows = result.unique().all()

    data = [
        UserCartaoSaude(
            user=row[0],
            cartao=row[1],
            tripulante=row[2] is not None,
            cemal_tem_ata=row[3] if row[1] and row[1].cemal else None,
            total_atas=row[4],
        )
        for row in rows
    ]

    return success_response(data=data)


@router.get(
    '/{cartao_id}',
    response_model=ApiResponse[CartaoSaudeWithUser],
)
async def get_cartao_saude_by_id(
    cartao_id: int,
    session: Session,
):
    """Busca cartao de saude por ID"""
    cartao = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.id == cartao_id)
    )

    if not cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao de saude nao encontrado',
        )

    return success_response(data=cartao)


@router.get(
    '/user/{user_id}',
    response_model=ApiResponse[CartaoSaudePublic],
)
async def get_cartao_saude_by_user(
    user_id: int,
    session: Session,
):
    """Busca cartao de saude por ID do usuario"""
    cartao = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.user_id == user_id)
    )

    if not cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=('Cartao de saude nao encontrado para este usuario'),
        )

    return success_response(data=cartao)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[CartaoSaudePublic],
)
async def create_cartao_saude(
    session: Session,
    dados: CartaoSaudeCreate,
):
    """Cria novo cartao de saude para um usuario"""
    user = await session.scalar(select(User).where(User.id == dados.user_id))
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuario nao encontrado',
        )

    cartao_existente = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.user_id == dados.user_id)
    )
    if cartao_existente:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=('Ja existe cartao de saude cadastrado para este usuario'),
        )

    dados_dict = dados.model_dump()
    new_cartao = CartaoSaude(**dados_dict)

    session.add(new_cartao)
    await session.commit()
    await session.refresh(new_cartao)

    return success_response(
        data=CartaoSaudePublic.model_validate(new_cartao),
        message='Cartao de saude criado com sucesso',
    )


@router.put(
    '/{cartao_id}',
    response_model=ApiResponse[None],
)
async def update_cartao_saude(
    cartao_id: int,
    session: Session,
    dados: CartaoSaudeUpdate,
):
    """Atualiza cartao de saude existente"""
    db_cartao = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.id == cartao_id)
    )

    if not db_cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao de saude nao encontrado',
        )

    for key, value in dados.model_dump(exclude_unset=True).items():
        setattr(db_cartao, key, value)

    await session.commit()
    await session.refresh(db_cartao)

    return success_response(message='Cartao de saude atualizado com sucesso')


@router.delete(
    '/{cartao_id}',
    response_model=ApiResponse[None],
)
async def delete_cartao_saude(
    cartao_id: int,
    session: Session,
):
    """Deleta cartao de saude"""
    db_cartao = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.id == cartao_id)
    )

    if not db_cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao de saude nao encontrado',
        )

    await session.delete(db_cartao)
    await session.commit()

    return success_response(message='Cartao de saude deletado com sucesso')
