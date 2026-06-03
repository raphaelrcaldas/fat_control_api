from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.instrucao.cartoes import Cartao
from fcontrol_api.models.shared.funcoes import Funcao
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.instrucao.cartoes import (
    CartoesPublic,
    CartoesUpdate,
    TripCartoesOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/cartoes', tags=['Instrucao'])


@router.get(
    '/',
    response_model=ApiResponse[list[TripCartoesOut]],
)
async def list_cartoes(
    session: Session,
):
    """Lista pilotos ativos com seus cartoes (idiomas e CVI)."""
    pilot_filter = exists(
        select(Funcao.func).where(
            Funcao.trip_id == Tripulante.id,
            Funcao.func == 'pil',
        )
    )

    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.id.label('user_id'),
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            User.saram,
            Cartao.id.label('cartao_id'),
            Cartao.ptai_validade,
            Cartao.tai_s_validade,
            Cartao.tai_s1_validade,
            Cartao.cvi_validade,
            Cartao.hab_espanhol,
            Cartao.val_espanhol,
            Cartao.hab_ingles,
            Cartao.val_ingles,
        )
        .select_from(Tripulante)
        .join(User, User.id == Tripulante.user_id)
        .join(PostoGrad, PostoGrad.short == User.p_g)
        .outerjoin(
            Cartao,
            Cartao.user_id == User.id,
        )
        .where(
            Tripulante.active.is_(True),
            User.active.is_(True),
        )
        .where(pilot_filter)
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
            User.id,
        )
    )

    rows = await session.execute(query)
    items = [
        TripCartoesOut(
            trip_id=r.trip_id,
            user_id=r.user_id,
            p_g=r.p_g,
            nome_guerra=r.nome_guerra,
            nome_completo=r.nome_completo,
            saram=r.saram,
            cartao=CartoesPublic(
                id=r.cartao_id,
                user_id=r.user_id,
                ptai_validade=r.ptai_validade,
                tai_s_validade=r.tai_s_validade,
                tai_s1_validade=r.tai_s1_validade,
                cvi_validade=r.cvi_validade,
                hab_espanhol=r.hab_espanhol,
                val_espanhol=r.val_espanhol,
                hab_ingles=r.hab_ingles,
                val_ingles=r.val_ingles,
            )
            if r.cartao_id is not None
            else None,
        )
        for r in rows.all()
    ]

    return success_response(data=items)


@router.put(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def upsert_cartao(
    trip_id: int,
    session: Session,
    dados: CartoesUpdate,
):
    """Cria ou atualiza o cartao (idiomas e CVI) de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    cartao = await session.scalar(
        select(Cartao).where(Cartao.user_id == tripulante.user_id)
    )

    if cartao:
        for key, value in dados.model_dump(exclude_unset=True).items():
            setattr(cartao, key, value)
        message = 'Cartao atualizado com sucesso'
    else:
        cartao = Cartao(
            user_id=tripulante.user_id,
            ptai_validade=dados.ptai_validade,
            tai_s_validade=dados.tai_s_validade,
            tai_s1_validade=dados.tai_s1_validade,
            cvi_validade=dados.cvi_validade,
            hab_espanhol=dados.hab_espanhol,
            val_espanhol=dados.val_espanhol,
            hab_ingles=dados.hab_ingles,
            val_ingles=dados.val_ingles,
        )
        session.add(cartao)
        message = 'Cartao cadastrado com sucesso'

    await session.commit()

    return success_response(message=message)


@router.delete(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def delete_cartao(
    trip_id: int,
    session: Session,
):
    """Remove o cartao (idiomas e CVI) de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    cartao = await session.scalar(
        select(Cartao).where(Cartao.user_id == tripulante.user_id)
    )
    if not cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao nao encontrado',
        )

    await session.delete(cartao)
    await session.commit()

    return success_response(message='Cartao removido com sucesso')
