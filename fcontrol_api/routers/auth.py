from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.auth import Token
from fcontrol_api.security import (
    create_access_token,
    get_current_user,
    verify_password,
)
from fcontrol_api.services.auth import token_data
from fcontrol_api.services.logs import log_user_action

router = APIRouter(prefix='/auth', tags=['auth'])

OAuth2Form = Annotated[OAuth2PasswordRequestForm, Depends()]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post('/token')
async def login_for_access_token(
    request: Request, form_data: OAuth2Form, session: Session
):
    saram = int(form_data.username)

    user = await session.scalar(select(User).where(User.saram == saram))
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Dados inválidos',
        )

    if not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Dados inválidos',
        )

    ip = request.client.host
    user_agent = request.headers.get('user-agent')

    await log_user_action(
        session=session,
        user_id=user.id,
        action='login',
        resource='auth',
        resource_id=None,
        before=None,
        after={'ip': ip, 'user_agent': user_agent},
    )

    await session.commit()

    data = await token_data(user, session)

    access_token = create_access_token(data=data)

    return {'access_token': access_token, 'token_type': 'bearer'}


@router.post('/refresh_token', response_model=Token)
async def refresh_access_token(
    session: Session, user: User = Depends(get_current_user)
):
    data = await token_data(user, session)

    new_access_token = create_access_token(data=data)

    return {'access_token': new_access_token, 'token_type': 'bearer'}


@router.post('/dev_login')
async def dev_login(
    user_id: int, session: Session, user: User = Depends(get_current_user)
):
    if not user or user.id != 1:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Not Allowed',
        )

    db_user = await session.scalar(select(User).where(User.id == user_id))

    data = await token_data(db_user, session)

    access_token = create_access_token(data=data, dev=True)

    return {'access_token': access_token, 'token_type': 'bearer'}
