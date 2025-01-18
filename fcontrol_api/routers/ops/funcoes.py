from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Tripulante
from fcontrol_api.schemas.funcoes import FuncSchema, FuncUpdate
from fcontrol_api.schemas.message import FuncMessage

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/funcoes', tags=['funcoes'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=FuncMessage)
async def create_funcao(funcao: FuncSchema, session: Session):
    db_trip = await session.scalar(
        select(Tripulante).where((Tripulante.id == funcao.trip_id))
    )

    if not db_trip:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Crew member not found',
        )

    db_func = await session.scalar(
        select(Funcao).where(
            (Funcao.func == funcao.func) & (Funcao.trip_id == funcao.trip_id)
        )
    )

    if db_func:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Função já registrada para esse tripulante',
        )

    new_func = Funcao(
        trip_id=funcao.trip_id,
        func=funcao.func,
        oper=funcao.oper,
        proj=funcao.proj,
        data_op=funcao.data_op,
    )  # type: ignore

    await session.add(new_func)  # type: ignore
    await session.commit()

    return {'detail': 'Função cadastrada com sucesso', 'data': new_func}


@router.put('/{id}', response_model=FuncMessage)
async def update_funcao(id, funcao: FuncUpdate, session: Session):
    db_func = await session.scalar(select(Funcao).where(Funcao.id == id))

    if not db_func:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew func not found'
        )

    for key, value in funcao.model_dump(exclude_unset=True).items():
        setattr(db_func, key, value)

    await session.commit()
    await session.refresh(db_func)

    return {'detail': 'Função atualizada com sucesso', 'data': db_func}


@router.delete('/{id}')
async def delete_func(id: int, session: Session):
    db_func = await session.scalar(select(Funcao).where(Funcao.id == id))

    if not db_func:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew function not found'
        )

    await session.delete(db_func)
    await session.commit()

    return {'detail': 'Função deletada'}
