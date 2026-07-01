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
from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.shared.users import User
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


def token_data(user: User, client: str, active_org: str | None = None):
    data = {
        'sub': f'{user.posto.short} {user.nome_guerra}',
        'user_id': user.id,
        'app_client': client,
        'first_login': user.first_login,
        'active_org': active_org,
    }

    return data


def create_access_token(data: dict, dev: bool = False):
    to_encode = data.copy()

    # Primeiro login: token de curta duração. A sessão só serve para a
    # troca de senha obrigatória; após a troca, o cliente reemite o token
    # (já com first_login=False) com a expiração normal.
    expire_minutes = (
        settings.FIRST_LOGIN_TOKEN_EXPIRE_MINUTES
        if data.get('first_login')
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(tz=ZoneInfo('UTC')) + timedelta(
        minutes=expire_minutes
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
    request: Request,
    session: Session,
    user: Annotated[User, Depends(get_current_user)],
):
    """Valida se o usuário é admin **na organização ativa** (do token).

    Os poderes acompanham a org ativa do `OrgSwitcher`: o vínculo admin
    deve existir para `(user, active_org)`. Senão, HTTP 403.
    """
    active_org = getattr(request.state, 'active_org', None)

    ur = await session.scalar(
        select(UserRole)
        .where(
            UserRole.user_id == user.id,
            UserRole.organizacao_id.is_not_distinct_from(active_org),
        )
        .options(joinedload(UserRole.role))
    )

    if not ur or not ur.role or (ur.role.name.lower() != 'admin'):
        # 'SCOPE_FORBIDDEN' é um código de contrato com o frontend:
        # o interceptor (services/Api.ts) o lê em `message` e redireciona
        # para /403. Sinaliza "rota proibida neste contexto" — distinto de
        # 403 de ação (ex.: _ensure_org_in_scope), que mantêm mensagem
        # humana e são tratados pelo caller (toast).
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail='SCOPE_FORBIDDEN'
        )

    return user


async def require_system_admin(
    request: Request,
    session: Session,
    user: Annotated[User, Depends(get_current_user)],
):
    """Valida admin com escopo de SISTEMA na org ativa.

    Exige org ativa NULL (contexto "Sistema") **e** vínculo admin com
    `organizacao_id IS NULL`. Um admin de sistema que alternou para uma
    unidade (active_org preenchido) perde os poderes de sistema enquanto
    estiver naquele contexto.
    """
    active_org = getattr(request.state, 'active_org', None)

    if active_org is not None:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail='SCOPE_FORBIDDEN'
        )

    ur = await session.scalar(
        select(UserRole)
        .where(
            UserRole.user_id == user.id,
            UserRole.organizacao_id.is_(None),
        )
        .options(joinedload(UserRole.role))
    )

    if not ur or not ur.role or ur.role.name.lower() != 'admin':
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail='SCOPE_FORBIDDEN'
        )

    return user


class AdminScope:
    """Escopo de admin resolvido pela org ativa do token.

    `is_system` indica admin global (contexto "Sistema", active_org NULL);
    caso contrário, `active_org` é a unidade à qual o admin está restrito.
    """

    def __init__(self, user: User, active_org: str | None):
        self.user = user
        self.active_org = active_org

    @property
    def is_system(self) -> bool:
        return self.active_org is None


async def get_admin_scope(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
) -> AdminScope:
    """Entrega o escopo do admin atual (reusa `require_admin` já validado)."""
    active_org = getattr(request.state, 'active_org', None)
    return AdminScope(user=user, active_org=active_org)


async def get_active_org(request: Request) -> str | None:
    """Org ativa do token (sigla). None = contexto 'Sistema' (sem lente)."""
    return getattr(request.state, 'active_org', None)


ActiveOrgOptional = Annotated[str | None, Depends(get_active_org)]


async def require_active_org(active_org: ActiveOrgOptional) -> str:
    """Exige uma org ativa no token.

    O data-plane (tripulantes, quadrinhos, escala, indisponibilidades,
    cartões de saúde, ordens de missão) é sempre escopado por unidade.
    Sem org ativa (contexto 'Sistema', sigla NULL) não há lente de unidade,
    então estas rotas respondem 400.
    """
    if active_org is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Selecione uma organização ativa para acessar estes dados',
        )
    return active_org


ActiveOrg = Annotated[str, Depends(require_active_org)]


async def has_permission(
    user: User,
    session: AsyncSession,
    resource: str,
    action: str,
) -> bool:
    """Retorna True se o usuário possuir a permissão (resource.action)."""
    user_data = await get_user_roles(user.id, session)
    if not user_data:
        return False
    return any(
        perm['resource'] == resource and perm['name'] == action
        for perm in user_data.get('perms', [])
    )


async def has_org_permission(
    user: User,
    session: AsyncSession,
    active_org: str | None,
    resource: str,
    action: str,
) -> bool:
    """Checa a permissão (resource.action) no vínculo da org ativa.

    Mesma resolução do `permission_checker`: admin da org tem bypass;
    senão, valida o grant no vínculo resolvido por `active_org` (não cai
    no fallback sem org, que emprestaria permissões de outra unidade).
    Use dentro do handler quando o gate depende do payload — ex.: exigir
    `ordem_missao.status.update` apenas quando há troca de status.
    """
    roles = await get_user_roles(user.id, session, active_org)
    if roles.get('role') == 'admin':
        return True
    return any(
        perm['resource'] == resource and perm['name'] == action
        for perm in roles.get('perms', [])
    )


def permission_checker(resource: str, action: str):
    async def check_permission(
        session: Session,
        active_org: ActiveOrgOptional,
        user: User = Depends(get_current_user),
    ) -> User:
        "Verifica se usuário tem permissão necessária."

        # Admin da organização ativa tem acesso total ao escopo dela: os
        # handlers de data-plane já filtram por `active_org`, então o
        # bypass não vaza dados de outras unidades. Resolve o vínculo pela
        # org ativa (não o de sistema), garantindo "só da org dele".
        roles = await get_user_roles(user.id, session, active_org)
        if roles.get('role') == 'admin':
            return user

        # Checa a permissão no MESMO vínculo resolvido pela org ativa.
        # `has_permission` re-consultaria sem org e o fallback de
        # `get_user_roles` aceitaria vínculo de outra organização —
        # permissão da org A autorizaria escrita na org B.
        allowed = any(
            perm['resource'] == resource and perm['name'] == action
            for perm in roles.get('perms', [])
        )
        if not allowed:
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


async def _deny_access(
    session: AsyncSession,
    user: User,
    resource: str,
    action: str,
    owner_id: int | None = None,
) -> None:
    """Registra a negação (auditoria `access_denied`) e levanta 403.

    Núcleo compartilhado pelos guards `ensure_permission_or_owner` e
    `ensure_org_permission_or_owner` — mantém uma única mensagem de log e um
    único formato de erro entre eles, evitando drift.
    """
    await log_user_action(
        session=session,
        user_id=user.id,
        action='access_denied',
        resource=resource,
        resource_id=owner_id,
        before=None,
        after=f"Tentou ação '{action}' sem permissão (owner_id={owner_id})",
    )

    raise HTTPException(
        status_code=HTTPStatus.FORBIDDEN,
        detail=f'Permissão negada: {resource}.{action}',
    )


async def ensure_permission_or_owner(
    user: User,
    session: AsyncSession,
    resource: str,
    action: str,
    owner_id: int,
) -> None:
    """Permite a ação se o usuário é o dono OU tem a permissão de role.

    Use em endpoints self-service onde a propriedade do recurso só é
    conhecida após carregar o registro ou ler o body. Para rotas
    administrativas puras, prefira `Depends(permission_checker(...))`.
    """
    if user.id == owner_id:
        return

    if await has_permission(user, session, resource, action):
        return

    await _deny_access(session, user, resource, action, owner_id)


async def ensure_org_permission_or_owner(
    user: User,
    session: AsyncSession,
    active_org: str | None,
    resource: str,
    action: str,
    owner_id: int | None,
) -> None:
    """Libera a ação se o usuário é o dono OU tem a permissão na org ativa.

    Versão org-scoped de `ensure_permission_or_owner`: usa
    `has_org_permission` (não `has_permission`), então NÃO empresta grants
    de outra unidade. Uso típico: leituras self-service que o portal FatBird
    consome — o próprio militar vê o seu dado sem role; terceiros exigem a
    permissão no vínculo da org ativa (admin tem bypass). `owner_id=None`
    representa "sem dono definido" (ex.: consulta ampla, sem filtro por
    usuário), caindo direto na checagem de permissão.
    """
    if owner_id is not None and user.id == owner_id:
        return

    if await has_org_permission(user, session, active_org, resource, action):
        return

    await _deny_access(session, user, resource, action, owner_id)
