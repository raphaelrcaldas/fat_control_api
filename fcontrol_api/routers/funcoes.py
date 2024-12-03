from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Funcao, Tripulante
from fcontrol_api.schemas.funcoes import BaseFunc, FuncSchema
from fcontrol_api.schemas.message import FuncMessage

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/funcoes', tags=['funcoes'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=FuncMessage)
def create_funcao(funcao: FuncSchema, session: Session):
    db_trip = session.scalar(
        select(Tripulante).where((Tripulante.id == funcao.trip_id))
    )

    if not db_trip:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Crew member not found',
        )

    db_func = session.scalar(
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
    )

    session.add(new_func)
    session.commit()

    return {'detail': 'Função cadastrada com sucesso', 'data': new_func}


@router.put('/{id}', response_model=FuncMessage)
def update_funcao(id, funcao: BaseFunc, session: Session):
    db_func = session.scalar(select(Funcao).where(Funcao.id == id))

    if not db_func:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew func not found'
        )

    for key, value in funcao.model_dump(exclude_unset=True).items():
        setattr(db_func, key, value)

    session.commit()
    session.refresh(db_func)

    return {'detail': 'Função atualizada com sucesso', 'data': db_func}


@router.delete('/{id}')
def delete_func(id: int, session: Session):
    db_func = session.scalar(select(Funcao).where(Funcao.id == id))

    if not db_func:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Crew function not found'
        )

    session.delete(db_func)
    session.commit()

    return {'detail': 'Função deletada'}
