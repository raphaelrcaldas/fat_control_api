from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import User
from fcontrol_api.schemas.message import (
    Message,
    UserList,
    UserPublic,
    UserSchema,
)
from fcontrol_api.security import get_password_hash

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/users', tags=['users'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=UserPublic)
def create_user(user: UserSchema, session: Session):
    db_user = session.scalar(select(User).where(User.saram == user.saram))

    if db_user:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='SARAM já registrado',
        )

    hashed_password = get_password_hash(user.password)

    db_user = User(
        email=user.email,
        username=user.username,
        password=hashed_password,
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    return db_user


@router.get('/', response_model=UserList)
def read_users(session: Session):
    users = session.scalars(select(User)).all()
    return {'users': users}


@router.put('/{user_id}', response_model=UserPublic)
def update_user(user_id: int, user: UserSchema, session: Session):
    query = select(User).where(User.id == user_id)

    user_search: User = session.scalar(query)

    if not user_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    hashed_password = get_password_hash(user.password)

    user_search.username = user.username
    user_search.password = hashed_password
    user_search.email = user.email

    session.commit()
    session.refresh(user_search)

    return user_search


@router.delete('/{user_id}', response_model=Message)
def delete_user(user_id: int, session: Session):
    query = select(User).where(User.id == user_id)

    user_search: User = session.scalar(query)

    if not user_search:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    session.delete(user_search)
    session.commit()

    return {'message': 'User deleted'}
