import base64
import hashlib
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from jwt import encode
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.services.auth import (
    get_user_roles,
    validate_user_client_access,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.settings import Settings

settings = Settings()
pwd_context = PasswordHash.recommended()

Session = Annotated[AsyncSession, Depends(get_session)]


def get_password_hash(password: str):
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def verify_pkce_challenge(code_verifier: str, code_challenge: str) -> bool:
    sha256_hash = hashlib.sha256(code_verifier.encode()).digest()
    code = base64.urlsafe_b64encode(sha256_hash).rstrip(b'=').decode()

    return code == code_challenge


def token_data(user: User, client: str):
    data = {
        'sub': f'{user.posto.short} {user.nome_guerra}',
        'user_id': user.id,
        'app_client': client,
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


async def get_current_user(request: Request, session: Session):
    # Verificar se middleware processou a autenticação
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED, detail='Não autenticado'
        )

    user_id = request.state.user_id

    # Buscar usuário no banco
    stmt = select(User).where(User.id == user_id)
    user = await session.scalar(stmt)

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Usuário não encontrado',
        )

    if not user.active:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail='Usuário inativo'
        )

    # Verificar permissões mínimas a cada requisição
    app_client = request.state.app_client
    if app_client:
        await validate_user_client_access(user.id, app_client, session)

    # Armazenar User em request.state
    request.state.current_user = user

    return user


async def require_admin(
    session: Session,
    user: Annotated[User, Depends(get_current_user)],
):
    """Dependência que valida se o usuário atual possui o perfil 'admin'.

    Retorna o usuário quando for administrador; senão levanta HTTP 403.
    """

    # busca o registro de user role do usuário atual
    ur = await session.scalar(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .options(joinedload(UserRole.role))
    )

    if not ur or not ur.role or (ur.role.name.lower() != 'admin'):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail='Permissão negada'
        )

    return user


def permission_checker(resource: str, action: str):
    async def check_permission(
        session: Session,
        user: User = Depends(get_current_user),
    ) -> User:
        "Verifica se usuário tem permissão necessária."

        # Buscar permissões do usuário
        user_data = await get_user_roles(user.id, session)

        if not user_data:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail='Usuário sem role atribuída',
            )

        # Verificar se tem a permissão necessária
        user_permissions = user_data.get('perms', [])

        has_permission = any(
            perm['resource'] == resource and perm['name'] == action
            for perm in user_permissions
        )

        if not has_permission:
            await log_user_action(
                session=session,
                user_id=user.id,
                action='access_denied',
                resource=resource,
                resource_id=None,
                before=None,
                after=f"Tentou ação '{action}' sem permissão",
            )

            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=f'Permissão negada: {resource}.{action}',
            )

        return user

    return check_permission
