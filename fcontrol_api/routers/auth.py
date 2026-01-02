import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Form,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.auth import (
    OAuth2AuthorizationCode,
    OAuth2Client,
)
from fcontrol_api.schemas.auth import Token
from fcontrol_api.security import (
    create_access_token,
    get_current_user,
    token_data,
    verify_password,
    verify_pkce_challenge,
)
from fcontrol_api.services.auth import validate_user_client_access
from fcontrol_api.services.logs import log_user_action

router = APIRouter(prefix='/auth', tags=['auth'])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.post('/authorize')
async def authorize(
    session: Session,
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    response_type: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form('S256'),
    saram: int = Form(...),
    password: str = Form(...),
):
    if response_type != 'code':
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail='Invalid response_type'
        )

    if code_challenge_method != 'S256':
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='code_challenge_method must be S256',
        )

    # 1. Validar o cliente
    client = await session.scalar(
        select(OAuth2Client).where(OAuth2Client.client_id == client_id)
    )
    if not client or client.redirect_uri != redirect_uri:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Invalid client or redirect_uri',
        )

    # 2. Autenticar o usuário
    user = await session.scalar(select(User).where(User.saram == saram))
    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED, detail='Credenciais inválidas'
        )

    # 2.1. Verficar se usuário esta ativo
    if not user.active:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Conta inativa. Contate o suporte',
        )

    # 2.5 Verificar permissões mínimas baseado no cliente
    await validate_user_client_access(user.id, client.client_id, session)

    # 3. Gerar e salvar o código de autorização de uso único
    auth_code = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    new_auth_code = OAuth2AuthorizationCode(
        code=auth_code,
        user_id=user.id,
        client_id=client.id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        expires_at=expires_at,
    )

    session.add(new_auth_code)
    await session.commit()

    return {'code': auth_code}


@router.post('/token', response_model=Token)
async def exchange_code_for_token(
    request: Request,
    session: Session,
    pkce_code_verifier: Annotated[str | None, Cookie()] = None,
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
):
    """
    Este endpoint troca um código de autorização válido por um access token.
    Ele espera que o code_verifier seja enviado em um cookie HttpOnly.
    """
    if grant_type != 'authorization_code':
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail='Unsupported grant_type'
        )

    if not pkce_code_verifier:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='PKCE code verifier cookie not found.',
        )

    # 1. Buscar o código de autorização no banco
    auth_code_obj = await session.scalar(
        select(OAuth2AuthorizationCode)
        .options(selectinload(OAuth2AuthorizationCode.client))
        .where(OAuth2AuthorizationCode.code == code)
    )

    if not auth_code_obj:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Invalid authorization code',
        )

    # 2. Validar o código (cliente, redirect_uri, expiração)
    if auth_code_obj.client.client_id != client_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail='Client ID mismatch'
        )
    if auth_code_obj.client.redirect_uri != redirect_uri:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail='Redirect URI mismatch'
        )
    if datetime.now(timezone.utc) > auth_code_obj.expires_at:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Authorization code expired',
        )

    # 3. Verificação PKCE (usando o verifier do cookie)
    if not verify_pkce_challenge(
        pkce_code_verifier, auth_code_obj.code_challenge
    ):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail='Invalid code_verifier'
        )

    # 4. Código válido, buscar o usuário e invalidar o código
    user = await session.get(User, auth_code_obj.user_id)
    await session.delete(auth_code_obj)  # Invalida o código de uso único

    if not user:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail='User not found for this authorization code',
        )

    # --- Geração de Token ---
    user_agent = request.headers.get('user-agent')

    await log_user_action(
        session=session,
        user_id=user.id,
        action='login',
        resource='auth',
        resource_id=None,
        before=None,
        after={'user_agent': user_agent, 'client': client_id},
    )

    await session.commit()

    data = token_data(user, client_id)
    access_token = create_access_token(data=data)

    return {
        'first_login': user.first_login,
        'access_token': access_token,
        'token_type': 'bearer',
    }


@router.post('/refresh_token', response_model=Token)
async def refresh_access_token(user: User = Depends(get_current_user)):
    data = token_data(user)
    new_access_token = create_access_token(data=data)
    return {'access_token': new_access_token, 'token_type': 'bearer'}


@router.post('/dev_login')
async def dev_login(
    user_id: int,
    session: Session,
    request: Request,
    user: User = Depends(get_current_user),
):
    """
    Endpoint exclusivo para desenvolvimento.
    Permite gerar token de qualquer usuário para testar diferentes perfis.

    Restrições:
    - Somente funciona em ambiente de desenvolvimento (ENV=development)
    - Somente o usuário com id=1 pode usar
    - Token expira em 7 dias
    """
    from fcontrol_api.settings import Settings

    settings = Settings()

    # Bloquear em produção
    if settings.ENV != 'development':
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Este endpoint só disponível em ambiente de desenvolvimento',
        )

    # Verificar se é o usuário admin (id=1)
    if not user or user.id != 1:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Apenas o administrador pode usar este endpoint',
        )

    # Buscar usuário alvo
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f'Usuário com id={user_id} não encontrado',
        )

    # Logging de auditoria
    await log_user_action(
        session=session,
        user_id=user.id,
        action='dev_login',
        resource='auth',
        resource_id=user_id,
        before=None,
        after={
            'target_user': f'{db_user.posto.short} {db_user.nome_guerra}'
            if db_user.posto
            else db_user.nome_guerra,
            'ip': request.client.host,
            'user_agent': request.headers.get('user-agent'),
        },
    )
    await session.commit()

    # Gerar token com expiração de 7 dias
    data = token_data(db_user, request.state.app_client)
    access_token = create_access_token(data=data, dev=True)

    return {
        'access_token': access_token,
        'token_type': 'bearer',
        'target_user': f'{db_user.posto.short} {db_user.nome_guerra}'
        if db_user.posto
        else db_user.nome_guerra,
        'expires_in_days': 7,
    }
