import base64
import hashlib
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import DecodeError, ExpiredSignatureError, decode, encode
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.settings import Settings

settings = Settings()
pwd_context = PasswordHash.recommended()

Session = Annotated[AsyncSession, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/token')


def get_password_hash(password: str):
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_pkce_code_challenge(code_verifier: str) -> str:
    """Cria um code_challenge a partir de um code_verifier usando S256."""
    sha256_hash = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b'=').decode()


def verify_pkce_challenge(code_verifier: str, code_challenge: str) -> bool:
    """Verifica se o code_verifier corresponde ao code_challenge."""
    return create_pkce_code_challenge(code_verifier) == code_challenge


def token_data(user: User):
    data = {
        'sub': f'{user.posto.short} {user.nome_guerra}',
        'user_id': user.id,
    }

    return data


def create_access_token(data: dict, dev: bool = False):
    to_encode = data.copy()
    expire = datetime.now(tz=ZoneInfo('UTC')) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    if dev:
        expire += timedelta(days=3650)

    to_encode.update({'exp': expire})
    encoded_jwt = encode(
        to_encode,
        base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


async def get_current_user(
    session: Session, token: str = Depends(oauth2_scheme)
):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Not authenticated',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    credentials_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    try:
        payload = decode(
            token,
            base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
            algorithms=[settings.ALGORITHM],
        )

        user_id: int = payload.get('user_id')

        if not user_id:
            raise credentials_exception

    except DecodeError:
        raise credentials_exception
    except ExpiredSignatureError:
        raise credentials_exception

    user = await session.scalar(select(User).where(User.id == user_id))

    if not user:
        raise credentials_exception

    return user


def verify_token(token: str | None):
    try:
        payload = decode(
            token,
            base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
            algorithms=[settings.ALGORITHM],
        )

        user_id: int = payload.get('user_id')

        if not user_id:
            return False

    except (DecodeError, ExpiredSignatureError):
        return False

    return True
