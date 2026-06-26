from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.funcoes import Funcao
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.funcoes import BaseFunc, FuncUpdate
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/trips/func', tags=['func'])


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=ApiResponse[None]
)
async def create_funcao(
    trip_id: int,
    funcao: BaseFunc,
    session: Session,
    active_org: ActiveOrg,
    _: Annotated[User, Depends(permission_checker('trips', 'create'))],
):
    db_trip = await session.scalar(
        select(Tripulante).where(
            (Tripulante.id == trip_id) & (Tripulante.uae == active_org)
        )
    )

    if not db_trip:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Tripulante não encontrado',
        )

    db_func = await session.scalar(
        select(Funcao).where(
            (Funcao.func == funcao.func) & (Funcao.trip_id == trip_id)
        )
    )

    if db_func:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Função já registrada para esse tripulante',
        )

    new_func = Funcao(
        trip_id=trip_id,
        func=funcao.func,
        oper=funcao.oper,
        proj=funcao.proj,
        data_op=funcao.data_op,
    )

    session.add(new_func)
    await session.commit()

    return success_response(message='Função cadastrada com sucesso')


@router.put('/{id}', response_model=ApiResponse[None])
async def update_funcao(
    id: int,
    funcao: FuncUpdate,
    session: Session,
    active_org: ActiveOrg,
    _: Annotated[User, Depends(permission_checker('trips', 'update'))],
):
    db_func = await session.scalar(
        select(Funcao)
        .join(Tripulante, Funcao.trip_id == Tripulante.id)
        .where((Funcao.id == id) & (Tripulante.uae == active_org))
    )

    if not db_func:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Função não encontrada'
        )

    for key, value in funcao.model_dump(exclude_unset=True).items():
        setattr(db_func, key, value)

    await session.commit()

    return success_response(message='Função atualizada com sucesso')


@router.delete('/{id}', response_model=ApiResponse[None])
async def delete_func(
    id: int,
    session: Session,
    active_org: ActiveOrg,
    _: Annotated[User, Depends(permission_checker('trips', 'delete'))],
):
    db_func = await session.scalar(
        select(Funcao)
        .join(Tripulante, Funcao.trip_id == Tripulante.id)
        .where((Funcao.id == id) & (Tripulante.uae == active_org))
    )

    if not db_func:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Função não encontrada'
        )

    await session.delete(db_func)
    await session.commit()

    return success_response(message='Função deletada')
