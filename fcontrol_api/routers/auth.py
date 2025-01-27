from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models import User
from fcontrol_api.schemas.auth import Token
from fcontrol_api.security import (
    create_access_token,
    get_current_user,
    verify_password,
)

router = APIRouter(prefix='/auth', tags=['auth'])

OAuth2Form = Annotated[OAuth2PasswordRequestForm, Depends()]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post('/token')
async def login_for_access_token(form_data: OAuth2Form, session: Session):
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

    data = {
        'sub': f'{user.posto.short} {user.nome_guerra}',
        'user_id': user.id,
        'scopes': [],
    }

    access_token = create_access_token(data=data)

    return {'access_token': access_token, 'token_type': 'bearer'}


@router.post('/refresh_token', response_model=Token)
def refresh_access_token(
    user: User = Depends(get_current_user),
):
    data = {
        'sub': f'{user.p_g} {user.nome_guerra}',
        'user_id': user.id,
        'scopes': [],
    }

    new_access_token = create_access_token(data=data)

    return {'access_token': new_access_token, 'token_type': 'bearer'}
