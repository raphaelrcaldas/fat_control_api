# 🔒 Plano de Implementação Zero Trust - FatControl API

**Data**: 2025-11-23
**Status**: Em Planejamento
**Versão**: 1.0

---

## 📊 Análise da Situação Atual

### ✅ O que já existe (Pontos Fortes)

1. **RBAC Completo**

   -  Resources → Permissions → Roles → Users
   -  Modelos em: `fcontrol_api/models/security/resources.py`
   -  Serviço: `fcontrol_api/services/auth.py::get_user_roles()`

2. **OAuth2 com PKCE**

   -  Authorization Code Flow implementado
   -  PKCE (SHA256) para proteção contra interceptação
   -  Endpoints: `/auth/authorize`, `/auth/token`

3. **JWT Authentication**

   -  Algoritmo: HS256
   -  Token payload: `{sub, user_id, exp}`
   -  TTL atual: 360 minutos (6 horas)

4. **Auditoria Básica**

   -  Tabela: `security.user_action_logs`
   -  Serviço: `fcontrol_api/services/logs.py::log_user_action()`
   -  Logs: login, CRUD de usuários, mudança de senha

5. **Password Security**
   -  Hashing: Argon2 (via pwdlib)
   -  Não armazena senhas em texto plano

### ❌ Gaps Críticos de Segurança

| Gap                                          | Impacto    | Prioridade |
| -------------------------------------------- | ---------- | ---------- |
| Permissões não são verificadas nos endpoints | ⚠️ CRÍTICO | P0         |
| Middleware de autenticação comentado         | ⚠️ CRÍTICO | P0         |
| Endpoints sem autenticação                   | ⚠️ CRÍTICO | P0         |
| Sem revogação de tokens                      | 🔴 ALTO    | P0         |
| Sem auditoria de leitura                     | 🔴 ALTO    | P1         |
| Sem rate limiting                            | 🔴 ALTO    | P1         |
| Token TTL muito longo (6h)                   | 🟡 MÉDIO   | P1         |
| Sem verificação contextual                   | 🟡 MÉDIO   | P2         |
| Sem MFA                                      | 🟡 MÉDIO   | P3         |

---

## 🎯 Princípios Zero Trust a Implementar

### 1. Never Trust, Always Verify

-  ✅ Verificar TODAS as requisições
-  ✅ Validar autenticação E autorização
-  ✅ Não confiar em requisições internas

### 2. Least Privilege Access

-  ✅ Usuários só acessam o que precisam
-  ✅ Permissões granulares por recurso/ação
-  ✅ Validar propriedade de recursos

### 3. Assume Breach

-  ✅ Tokens podem ser comprometidos → revogação
-  ✅ Senhas podem vazar → MFA
-  ✅ Rede pode ser hostil → criptografia

### 4. Verify Explicitly

-  ✅ Verificar contexto (IP, device, localização)
-  ✅ Verificar em cada requisição, não apenas no login
-  ✅ Auditoria completa de acessos

### 5. Microsegmentation

-  ✅ Controle de acesso por endpoint
-  ✅ Separação por schemas (public, security, cegep)
-  ✅ Isolamento de recursos sensíveis

---

## 🚀 Fases de Implementação

## FASE 1: Fundação Crítica (P0) 🔴

### 1.1 Sistema de Revogação de Tokens

**Objetivo**: Permitir logout e invalidação de tokens comprometidos

#### Modelo: `TokenBlacklist`

**Arquivo**: `fcontrol_api/models/security/token_blacklist.py` ✅ CRIADO

```python
class TokenBlacklist(Base):
    __tablename__ = 'token_blacklist'

    id: Mapped[int]
    token: Mapped[str]  # indexed, unique
    user_id: Mapped[int]  # FK to users
    revoked_at: Mapped[datetime]
    reason: Mapped[str]  # logout, password_change, admin_revoke, suspicious
    expires_at: Mapped[datetime]  # Para limpeza automática
```

#### Migration

**Arquivo**: `migrations/versions/XXXXX_token_blacklist_zero_trust.py` ⏳ PENDENTE

```python
def upgrade() -> None:
    op.create_table('token_blacklist',
        sa.Column('id', sa.Integer(), sa.Identity(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
        schema='security'
    )
    op.create_index('ix_token_blacklist_token', 'token_blacklist', ['token'], schema='security')
```

#### Serviços de Revogação

**Arquivo**: `fcontrol_api/security.py` ⏳ ADICIONAR

```python
# ============ SERVIÇOS DE REVOGAÇÃO DE TOKENS ============

async def revoke_token(
    token: str,
    user_id: int,
    reason: str,
    session: AsyncSession
) -> None:
    """
    Adiciona token à blacklist.

    Args:
        token: JWT token completo
        user_id: ID do usuário
        reason: 'logout', 'password_change', 'admin_revoke', 'suspicious_activity'
        session: Sessão do banco
    """
    from jose import jwt
    from fcontrol_api.models.security.token_blacklist import TokenBlacklist
    from fcontrol_api.settings import Settings

    # Decode para pegar expiration
    try:
        payload = jwt.decode(
            token,
            base64.urlsafe_b64decode(Settings().SECRET_KEY + '========'),
            algorithms=[Settings().ALGORITHM]
        )
        expires_at = datetime.fromtimestamp(payload['exp'])
    except:
        # Se não conseguir decodificar, assume expiração em 1 dia
        expires_at = datetime.utcnow() + timedelta(days=1)

    blacklist_entry = TokenBlacklist(
        token=token,
        user_id=user_id,
        reason=reason,
        expires_at=expires_at
    )

    session.add(blacklist_entry)
    await session.commit()


async def is_token_blacklisted(token: str, session: AsyncSession) -> bool:
    """Verifica se token está na blacklist."""
    from fcontrol_api.models.security.token_blacklist import TokenBlacklist
    from sqlalchemy import select

    stmt = select(TokenBlacklist).where(TokenBlacklist.token == token)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def revoke_all_user_tokens(user_id: int, reason: str, session: AsyncSession) -> int:
    """
    Revoga todos os tokens ativos de um usuário.
    Usado em: mudança de senha, bloqueio de conta.

    Returns:
        Número de tokens revogados (simulado - tokens são stateless)
    """
    # Como tokens são stateless (JWT), não temos lista de tokens ativos
    # Alternativa: marcar user_id + timestamp na blacklist e verificar na validação
    # Por ora, retornamos 0 e documentamos a limitação
    # TODO: Implementar sessão ativa para rastreamento real de tokens
    return 0


async def cleanup_expired_blacklist(session: AsyncSession) -> int:
    """
    Remove tokens expirados da blacklist (executar via cron job).

    Returns:
        Número de tokens removidos
    """
    from fcontrol_api.models.security.token_blacklist import TokenBlacklist
    from sqlalchemy import delete

    stmt = delete(TokenBlacklist).where(
        TokenBlacklist.expires_at < datetime.utcnow()
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
```

#### Atualizar `verify_token()`

**Arquivo**: `fcontrol_api/security.py` (linhas 139-155) ⏳ MODIFICAR

```python
# ANTES
def verify_token(token: str) -> bool:
    try:
        payload = decode(
            token,
            base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
            algorithms=[settings.ALGORITHM],
        )
        return bool(payload.get('user_id'))
    except (JWTError, ValidationError):
        return False

# DEPOIS
async def verify_token(token: str, session: AsyncSession = None) -> bool:
    """
    Verifica se token é válido E não está revogado.

    Args:
        token: JWT token
        session: Sessão do banco (opcional para verificar blacklist)
    """
    try:
        payload = decode(
            token,
            base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
            algorithms=[settings.ALGORITHM],
        )

        if not payload.get('user_id'):
            return False

        # Zero Trust: Verificar se token foi revogado
        if session:
            if await is_token_blacklisted(token, session):
                return False

        return True

    except (JWTError, ValidationError):
        return False
```

---

### 1.3 Decorator de Permissões

**Objetivo**: Verificar permissões granulares em cada endpoint

**Arquivo**: `fcontrol_api/dependencies/permissions.py` 🆕 CRIAR

```python
"""
Dependências de autorização para Zero Trust.

Implementa verificação granular de permissões baseada em RBAC.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.security import get_current_user
from fcontrol_api.services.auth import get_user_roles


class PermissionChecker:
    """
    Checker de permissões reutilizável.

    Uso:
        @router.get('/users/')
        async def list_users(
            user: User = Depends(require_permission('users', 'read'))
        ):
            ...
    """

    def __init__(self, resource: str, action: str):
        """
        Args:
            resource: Nome do recurso (ex: 'users', 'missoes')
            action: Ação requerida (ex: 'read', 'write', 'delete')
        """
        self.resource = resource
        self.action = action

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> User:
        """
        Verifica se usuário tem permissão necessária.

        Returns:
            User object se autorizado

        Raises:
            HTTPException 403 se não autorizado
        """
        # Buscar permissões do usuário
        user_data = await get_user_roles(user.id, session)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Usuário sem role atribuída'
            )

        # Verificar se tem a permissão necessária
        user_permissions = user_data.get('perms', [])

        has_permission = any(
            perm['resource'] == self.resource and perm['name'] == self.action
            for perm in user_permissions
        )

        if not has_permission:
            # Log de tentativa de acesso negado
            from fcontrol_api.services.logs import log_user_action
            await log_user_action(
                session=session,
                user_id=user.id,
                action='access_denied',
                resource=self.resource,
                resource_id=None,
                before=None,
                after=f"Tentou ação '{self.action}' sem permissão"
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Permissão negada: {self.resource}.{self.action}'
            )

        return user


def require_permission(resource: str, action: str):
    """
    Factory function para criar checkers de permissão.

    Uso:
        require_permission('users', 'read')
        require_permission('missoes', 'write')
        require_permission('logs', 'delete')
    """
    return PermissionChecker(resource, action)


# Atalhos para permissões comuns
def require_read(resource: str):
    """Requer permissão de leitura."""
    return require_permission(resource, 'read')


def require_write(resource: str):
    """Requer permissão de escrita."""
    return require_permission(resource, 'write')


def require_delete(resource: str):
    """Requer permissão de deleção."""
    return require_permission(resource, 'delete')
```

**Criar `__init__.py`**:
**Arquivo**: `fcontrol_api/dependencies/__init__.py` 🆕 CRIAR

```python
from .permissions import require_permission, require_read, require_write, require_delete

__all__ = ['require_permission', 'require_read', 'require_write', 'require_delete']
```

---

### 1.4 Auditoria Completa

**Objetivo**: Auditar TODAS as operações (leitura e escrita)

#### Expandir Modelo de Logs

**Arquivo**: Migration nova ⏳ CRIAR

```python
# Adicionar campos ao user_action_logs
def upgrade() -> None:
    op.add_column('user_action_logs',
        sa.Column('ip_address', sa.String(), nullable=True),
        schema='security'
    )
    op.add_column('user_action_logs',
        sa.Column('user_agent', sa.String(), nullable=True),
        schema='security'
    )
    op.add_column('user_action_logs',
        sa.Column('request_method', sa.String(), nullable=True),
        schema='security'
    )
    op.add_column('user_action_logs',
        sa.Column('request_path', sa.String(), nullable=True),
        schema='security'
    )
```

#### Atualizar Serviço de Logs

**Arquivo**: `fcontrol_api/services/logs.py` ⏳ MODIFICAR

```python
async def log_user_action(
    session,
    user_id: int,
    action: str,
    resource: str,
    resource_id: int | None = None,
    before: Any | None = None,
    after: Any | None = None,
    # NOVOS CAMPOS ZERO TRUST
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_method: str | None = None,
    request_path: str | None = None,
):
    """
    Loga ação do usuário com contexto completo (Zero Trust).

    Novos campos permitem:
    - Rastreamento de origem da requisição
    - Detecção de anomalias (IP/device incomum)
    - Auditoria forense completa
    """
    log = UserActionLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        before=json.dumps(before) if before else None,
        after=json.dumps(after) if after else None,
        ip_address=ip_address,
        user_agent=user_agent,
        request_method=request_method,
        request_path=request_path,
    )
    session.add(log)
    await session.commit()
```

#### Middleware de Auditoria Automática

**Arquivo**: `fcontrol_api/middlewares.py` ⏳ ADICIONAR

```python
async def audit_middleware(request: Request, call_next):
    """
    Audita automaticamente todas as requisições autenticadas.

    Zero Trust: Log completo de acessos para detecção de anomalias.
    """
    # Processar requisição
    response = await call_next(request)

    # Auditar apenas se autenticado
    if hasattr(request.state, 'security_context'):
        # Extrair user_id do token (evitar query adicional)
        token = request.state.security_context['token']
        try:
            from jose import jwt
            from fcontrol_api.settings import Settings
            import base64

            payload = jwt.decode(
                token,
                base64.urlsafe_b64decode(Settings().SECRET_KEY + '========'),
                algorithms=[Settings().ALGORITHM]
            )
            user_id = payload.get('user_id')

            if user_id:
                # Log assíncrono (não bloqueia resposta)
                # TODO: Implementar queue para não sobrecarregar DB
                from fcontrol_api.database import get_session
                async with get_session() as session:
                    await log_user_action(
                        session=session,
                        user_id=user_id,
                        action=request.method.lower(),
                        resource=request.url.path,
                        ip_address=request.client.host,
                        user_agent=request.headers.get('user-agent'),
                        request_method=request.method,
                        request_path=request.url.path,
                    )
        except Exception as e:
            # Não falhar a requisição por erro de auditoria
            logger.error(f"Erro ao auditar requisição: {e}")

    return response
```

---

### 1.5 Revogar Tokens ao Trocar Senha

**Arquivo**: `fcontrol_api/routers/users.py` ⏳ MODIFICAR

Localizar endpoint de mudança de senha e adicionar:

```python
@router.patch('/users/{user_id}/password')
async def change_password(
    user_id: int,
    password_data: PasswordChangeSchema,
    session: Session,
    current_user: User = Depends(get_current_user),
):
    # ... validações existentes ...

    # Atualizar senha
    user.password = get_password_hash(password_data.new_password)

    # ADICIONAR: Revogar todos os tokens do usuário
    from fcontrol_api.security import revoke_all_user_tokens
    revoked_count = await revoke_all_user_tokens(
        user_id=user.id,
        reason='password_change',
        session=session
    )

    # Log
    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='password_change',
        resource='users',
        resource_id=user.id,
        after=f'Tokens revogados: {revoked_count}'
    )

    session.add(user)
    await session.commit()

    return {'message': 'Senha alterada. Faça login novamente.'}
```

---

## FASE 2: Aplicar Permissões em Endpoints (P0)

### 2.1 Mapeamento: Endpoint → Permissão

**Arquivo**: `ENDPOINT_PERMISSIONS_MAP.md` 🆕 CRIAR (para referência)

| Endpoint           | Método | Resource | Action | Nota                  |
| ------------------ | ------ | -------- | ------ | --------------------- |
| `/users/`          | GET    | users    | read   | Lista usuários        |
| `/users/`          | POST   | users    | write  | Criar usuário         |
| `/users/{id}`      | GET    | users    | read   | Ver usuário           |
| `/users/{id}`      | PATCH  | users    | write  | Editar usuário        |
| `/users/{id}`      | DELETE | users    | delete | Deletar usuário       |
| `/security/roles/` | GET    | roles    | read   | Admin only            |
| `/security/roles/` | POST   | roles    | write  | Admin only            |
| `/indisp/`         | GET    | indisp   | read   | -                     |
| `/indisp/`         | POST   | indisp   | write  | -                     |
| `/logs/`           | GET    | logs     | read   | Admin only            |
| `/cegep/missoes/`  | GET    | missoes  | read   | -                     |
| `/cegep/missoes/`  | POST   | missoes  | write  | -                     |
| `/ops/quads/`      | GET    | quads    | read   | ⚠️ Atualmente público |
| `/ops/quads/`      | POST   | quads    | write  | ⚠️ Atualmente público |

### 2.2 Exemplo de Aplicação

**Arquivo**: `fcontrol_api/routers/users.py` ⏳ MODIFICAR TODOS

```python
from fcontrol_api.dependencies import require_permission, require_read, require_write

# ANTES
@router.get('/users/')
async def list_users(
    session: Session,
    user: User = Depends(get_current_user),  # Apenas autenticação
):
    ...

# DEPOIS
@router.get('/users/')
async def list_users(
    session: Session,
    user: User = Depends(require_read('users')),  # Autenticação + Autorização
):
    ...

# ANTES
@router.post('/users/')
async def create_user(
    user_data: UserCreateSchema,
    session: Session,
    user: User = Depends(get_current_user),
):
    ...

# DEPOIS
@router.post('/users/')
async def create_user(
    user_data: UserCreateSchema,
    session: Session,
    user: User = Depends(require_write('users')),
):
    ...
```

### 2.3 Checklist de Routers a Atualizar

-  [ ] `routers/users.py` - 8 endpoints
-  [ ] `routers/security.py` - Já usa `require_admin` (converter para require_permission)
-  [ ] `routers/indisp.py` - 5 endpoints
-  [ ] `routers/logs.py` - 2 endpoints
-  [ ] `routers/postos.py` - 3 endpoints
-  [ ] `routers/cities.py` - 3 endpoints ⚠️ Atualmente públicos
-  [ ] `routers/ops/quads.py` - 4 endpoints ⚠️ Atualmente públicos
-  [ ] `routers/ops/funcoes.py` - 3 endpoints
-  [ ] `routers/ops/tripulantes.py` - 4 endpoints
-  [ ] `routers/cegep/missao.py` - 6 endpoints
-  [ ] `routers/cegep/comiss.py` - 4 endpoints
-  [ ] `routers/cegep/financeiro.py` - 3 endpoints
-  [ ] `routers/cegep/dados_bancarios.py` - 5 endpoints

**Total**: ~53 endpoints a atualizar

---

## FASE 3: Sessões e Rate Limiting (P1)

### 3.1 Adicionar Redis

**Arquivo**: `pyproject.toml` ⏳ ADICIONAR

```toml
[tool.poetry.dependencies]
redis = "^5.0.0"
```

**Arquivo**: `fcontrol_api/redis_client.py` 🆕 CRIAR

```python
"""Cliente Redis para cache e sessões."""

import redis.asyncio as redis
from fcontrol_api.settings import Settings

settings = Settings()

# Pool de conexões reutilizável
redis_client = redis.from_url(
    settings.REDIS_URL,
    encoding='utf-8',
    decode_responses=True,
    max_connections=10
)

async def get_redis():
    """Dependency para usar Redis em endpoints."""
    return redis_client
```

**Arquivo**: `.env` ⏳ ADICIONAR

```env
REDIS_URL=redis://localhost:6379/0
```

### 3.2 Gerenciamento de Sessões

**Arquivo**: `fcontrol_api/services/sessions.py` 🆕 CRIAR

```python
"""
Gerenciamento de sessões ativas - Zero Trust.

Permite:
- Rastrear sessões ativas por usuário
- Limitar sessões concorrentes
- Revogar sessão específica
- Ver histórico de sessões
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import redis.asyncio as redis


class SessionManager:
    """Gerencia sessões de usuários no Redis."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.session_prefix = "session:"
        self.user_sessions_prefix = "user_sessions:"
        self.max_sessions_per_user = 3  # Limite de sessões concorrentes

    async def create_session(
        self,
        token: str,
        user_id: int,
        ip: str,
        user_agent: str,
        expires_in_minutes: int = 360
    ) -> str:
        """
        Cria nova sessão.

        Returns:
            session_id
        """
        session_id = f"{user_id}:{token[:16]}"  # Prefixo único
        session_key = f"{self.session_prefix}{session_id}"

        session_data = {
            'user_id': user_id,
            'token': token,
            'ip': ip,
            'user_agent': user_agent,
            'created_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat(),
        }

        # Armazenar sessão com TTL
        await self.redis.setex(
            session_key,
            timedelta(minutes=expires_in_minutes),
            json.dumps(session_data)
        )

        # Adicionar ao set de sessões do usuário
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        await self.redis.sadd(user_sessions_key, session_id)

        # Verificar limite de sessões
        await self._enforce_session_limit(user_id)

        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Busca dados da sessão."""
        session_key = f"{self.session_prefix}{session_id}"
        data = await self.redis.get(session_key)
        return json.loads(data) if data else None

    async def get_user_sessions(self, user_id: int) -> List[Dict]:
        """Lista todas as sessões ativas de um usuário."""
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        session_ids = await self.redis.smembers(user_sessions_key)

        sessions = []
        for session_id in session_ids:
            session_data = await self.get_session(session_id)
            if session_data:
                session_data['session_id'] = session_id
                sessions.append(session_data)
            else:
                # Limpar sessão expirada do set
                await self.redis.srem(user_sessions_key, session_id)

        return sessions

    async def revoke_session(self, session_id: str) -> bool:
        """Revoga sessão específica."""
        session_data = await self.get_session(session_id)
        if not session_data:
            return False

        user_id = session_data['user_id']

        # Remover sessão
        session_key = f"{self.session_prefix}{session_id}"
        await self.redis.delete(session_key)

        # Remover do set do usuário
        user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
        await self.redis.srem(user_sessions_key, session_id)

        return True

    async def revoke_all_user_sessions(self, user_id: int) -> int:
        """Revoga todas as sessões de um usuário."""
        sessions = await self.get_user_sessions(user_id)

        for session in sessions:
            await self.revoke_session(session['session_id'])

        return len(sessions)

    async def update_activity(self, session_id: str):
        """Atualiza timestamp de última atividade."""
        session_data = await self.get_session(session_id)
        if session_data:
            session_data['last_activity'] = datetime.utcnow().isoformat()
            session_key = f"{self.session_prefix}{session_id}"
            # Manter TTL original
            ttl = await self.redis.ttl(session_key)
            await self.redis.setex(
                session_key,
                ttl if ttl > 0 else 3600,
                json.dumps(session_data)
            )

    async def _enforce_session_limit(self, user_id: int):
        """Remove sessões mais antigas se exceder limite."""
        sessions = await self.get_user_sessions(user_id)

        if len(sessions) > self.max_sessions_per_user:
            # Ordenar por created_at
            sessions.sort(key=lambda s: s['created_at'])

            # Revogar as mais antigas
            excess = len(sessions) - self.max_sessions_per_user
            for session in sessions[:excess]:
                await self.revoke_session(session['session_id'])
```

### 3.3 Rate Limiting

**Arquivo**: `pyproject.toml` ⏳ ADICIONAR

```toml
slowapi = "^0.1.9"
```

**Arquivo**: `fcontrol_api/app.py` ⏳ MODIFICAR

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Criar limiter
limiter = Limiter(key_func=get_remote_address)

# Adicionar ao app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

**Arquivo**: `fcontrol_api/routers/auth.py` ⏳ MODIFICAR

```python
from slowapi import Limiter
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

@router.post('/authorize')
@limiter.limit("5/minute")  # Máximo 5 tentativas de login por minuto
async def authorize(request: Request, ...):
    ...

@router.post('/token')
@limiter.limit("5/minute")
async def token(request: Request, ...):
    ...
```

---

## FASE 4: Segurança Avançada (P2)

### 4.1 Reduzir Token TTL e Implementar Refresh

**Arquivo**: `.env` ⏳ MODIFICAR

```env
# ANTES
ACCESS_TOKEN_EXPIRE_MINUTES=360  # 6 horas

# DEPOIS
ACCESS_TOKEN_EXPIRE_MINUTES=30   # 30 minutos
REFRESH_TOKEN_EXPIRE_DAYS=7      # 7 dias
```

### 4.2 Security Headers Middleware

**Arquivo**: `fcontrol_api/middlewares/security_headers.py` 🆕 CRIAR

```python
"""Middleware de security headers."""

from fastapi import Request


async def security_headers_middleware(request: Request, call_next):
    """Adiciona headers de segurança a todas as respostas."""
    response = await call_next(request)

    # HSTS - Force HTTPS
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    # Prevenir clickjacking
    response.headers['X-Frame-Options'] = 'DENY'

    # Prevenir MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # XSS Protection
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # Content Security Policy
    response.headers['Content-Security-Policy'] = "default-src 'self'"

    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Permissions Policy
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

    return response
```

### 4.3 Migrar para RS256 (Assimétrico)

**Benefício**: Chave privada assina, chave pública valida. Comprometimento de um serviço de validação não expõe capacidade de criar tokens.

**Arquivo**: `fcontrol_api/settings.py` ⏳ ADICIONAR

```python
class Settings(BaseSettings):
    # ... existentes ...

    # RS256 - Chaves assimétricas
    PRIVATE_KEY_PATH: str = './keys/private_key.pem'
    PUBLIC_KEY_PATH: str = './keys/public_key.pem'
    ALGORITHM: str = 'RS256'  # Mudar de HS256
```

**Gerar chaves** (via bash):

```bash
# Criar diretório
mkdir -p keys

# Gerar chave privada RSA 4096-bit
openssl genrsa -out keys/private_key.pem 4096

# Extrair chave pública
openssl rsa -in keys/private_key.pem -pubout -out keys/public_key.pem

# Adicionar ao .gitignore
echo "keys/private_key.pem" >> .gitignore
```

---

## FASE 5: MFA e Monitoramento (P3)

### 5.1 Multi-Factor Authentication (TOTP)

**Arquivo**: `pyproject.toml` ⏳ ADICIONAR

```toml
pyotp = "^2.9.0"
qrcode = { extras = ["pil"], version = "^7.4.2" }
```

**Modelo**:

```python
class UserMFA(Base):
    __tablename__ = 'user_mfa'

    id: Mapped[int]
    user_id: Mapped[int]  # FK unique
    secret: Mapped[str]   # TOTP secret (encrypted)
    enabled: Mapped[bool]
    backup_codes: Mapped[str]  # JSON array
    created_at: Mapped[datetime]
```

**Endpoints**:

-  `POST /auth/mfa/enable` - Gera QR code
-  `POST /auth/mfa/verify` - Valida código TOTP
-  `POST /auth/mfa/disable` - Desabilita MFA
-  `GET /auth/mfa/backup-codes` - Regenera códigos de backup

---

## 📊 Recursos e Permissões Necessários

### Recursos a Criar no Banco

```sql
-- Executar após implementação
INSERT INTO security.resources (name, description) VALUES
  ('users', 'Gerenciamento de usuários'),
  ('roles', 'Gerenciamento de roles'),
  ('permissions', 'Gerenciamento de permissões'),
  ('logs', 'Visualização de logs de auditoria'),
  ('indisp', 'Gerenciamento de indisponibilidades'),
  ('missoes', 'Gerenciamento de missões'),
  ('comissoes', 'Gerenciamento de comissões'),
  ('financeiro', 'Gestão financeira'),
  ('quads', 'Gerenciamento de quadrantes'),
  ('funcoes', 'Funções operacionais'),
  ('tripulantes', 'Gerenciamento de tripulantes'),
  ('postos', 'Postos e graduações'),
  ('cities', 'Cidades');

-- Permissões básicas para cada recurso
INSERT INTO security.permissions (resource_id, name, description)
SELECT r.id, 'read', 'Visualizar ' || r.name
FROM security.resources r;

INSERT INTO security.permissions (resource_id, name, description)
SELECT r.id, 'write', 'Criar/editar ' || r.name
FROM security.resources r;

INSERT INTO security.permissions (resource_id, name, description)
SELECT r.id, 'delete', 'Deletar ' || r.name
FROM security.resources r;
```

---

## ✅ Checklist de Implementação

### Fase 1 - Fundação Crítica

-  [x] Criar modelo `TokenBlacklist`
-  [ ] Criar migration `token_blacklist`
-  [ ] Implementar serviços de revogação em `security.py`
-  [ ] Atualizar `verify_token()` para checar blacklist
-  [ ] Criar endpoint `POST /auth/logout`
-  [ ] Criar decorator `@require_permission()`
-  [ ] Ativar middleware de autenticação global
-  [ ] Expandir `log_user_action()` com contexto
-  [ ] Criar middleware de auditoria automática
-  [ ] Revogar tokens ao trocar senha

### Fase 2 - Autorização Granular

-  [ ] Criar `ENDPOINT_PERMISSIONS_MAP.md`
-  [ ] Aplicar decorators em 53 endpoints
-  [ ] Criar permissões no banco (SQL acima)
-  [ ] Testar fluxo completo de autorização
-  [ ] Documentar permissões necessárias por role

### Fase 3 - Sessões e Rate Limiting

-  [ ] Adicionar Redis ao projeto
-  [ ] Implementar `SessionManager`
-  [ ] Criar sessão ao gerar token
-  [ ] Adicionar rate limiting com slowapi
-  [ ] Configurar limites por endpoint

### Fase 4 - Segurança Avançada

-  [ ] Reduzir token TTL para 30min
-  [ ] Implementar refresh token rotation
-  [ ] Criar middleware de security headers
-  [ ] Gerar par de chaves RSA
-  [ ] Migrar de HS256 para RS256

### Fase 5 - MFA e Monitoramento

-  [ ] Adicionar pyotp e qrcode
-  [ ] Criar modelo `UserMFA`
-  [ ] Implementar endpoints de MFA
-  [ ] Tornar MFA obrigatório para admin
-  [ ] Criar dashboard de segurança

---

## 🧪 Testes Recomendados

### Testes de Autenticação

```python
# test_auth_zero_trust.py

async def test_access_without_token_denied():
    """Requisição sem token deve ser negada."""
    response = client.get('/users/')
    assert response.status_code == 401

async def test_access_with_revoked_token_denied():
    """Token revogado não deve permitir acesso."""
    # Fazer login
    token = login()
    # Fazer logout (revoga token)
    logout(token)
    # Tentar acessar com token revogado
    response = client.get('/users/', cookies={'token': token})
    assert response.status_code == 401

async def test_permission_check_enforced():
    """Usuário sem permissão não deve acessar."""
    # Login como usuário sem permissão 'users.write'
    token = login_as('user_readonly')
    # Tentar criar usuário
    response = client.post('/users/', json={...}, cookies={'token': token})
    assert response.status_code == 403

async def test_password_change_revokes_tokens():
    """Trocar senha deve revogar tokens antigos."""
    token = login()
    change_password(token, 'new_pass')
    # Token antigo não deve funcionar mais
    response = client.get('/users/', cookies={'token': token})
    assert response.status_code == 401
```

### Testes de Rate Limiting

```python
async def test_rate_limit_login():
    """Deve bloquear após 5 tentativas em 1 minuto."""
    for i in range(6):
        response = login_attempt()
        if i < 5:
            assert response.status_code in [200, 401]
        else:
            assert response.status_code == 429  # Too Many Requests
```

---

## 📚 Referências

### Documentação

-  [NIST Zero Trust Architecture](https://www.nist.gov/publications/zero-trust-architecture)
-  [OAuth 2.0 RFC 6749](https://datatracker.ietf.org/doc/html/rfc6749)
-  [PKCE RFC 7636](https://datatracker.ietf.org/doc/html/rfc7636)
-  [JWT RFC 7519](https://datatracker.ietf.org/doc/html/rfc7519)

### Bibliotecas

-  [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
-  [PyJWT](https://pyjwt.readthedocs.io/)
-  [SlowAPI](https://slowapi.readthedocs.io/)
-  [PyOTP](https://pyauth.github.io/pyotp/)

---

## 🔄 Notas de Manutenção

### Limpeza Periódica (Cron Jobs)

```python
# scripts/cleanup_security.py

async def cleanup_expired_blacklist():
    """Rodar diariamente - remove tokens expirados da blacklist."""
    async with get_session() as session:
        count = await cleanup_expired_blacklist(session)
        print(f"Removidos {count} tokens expirados")

async def cleanup_old_logs():
    """Rodar semanalmente - arquiva logs com mais de 90 dias."""
    # Implementar conforme política de retenção
    pass
```

### Rotação de Chaves

```bash
# scripts/rotate_keys.sh
# Executar mensalmente

# Gerar novo par de chaves
openssl genrsa -out keys/private_key_new.pem 4096
openssl rsa -in keys/private_key_new.pem -pubout -out keys/public_key_new.pem

# Fase de transição: validar com ambas as chaves públicas
# Após período de graça (ex: 24h), remover chave antiga
mv keys/private_key.pem keys/private_key_old.pem
mv keys/private_key_new.pem keys/private_key.pem
mv keys/public_key_new.pem keys/public_key.pem

# Revogar todos os tokens antigos (forçar re-login)
# python scripts/revoke_all_tokens.py
```

---

## 🎯 Métricas de Sucesso

Após implementação completa, o sistema deve atender:

-  ✅ **100% dos endpoints** protegidos por autenticação
-  ✅ **100% dos endpoints** protegidos por autorização granular
-  ✅ **100% das operações** auditadas (read + write)
-  ✅ **Logout funcional** com revogação de tokens
-  ✅ **Rate limiting** ativo em endpoints críticos
-  ✅ **Token TTL ≤ 30 minutos**
-  ✅ **Sessões rastreadas** em tempo real
-  ✅ **MFA disponível** para roles críticas
-  ✅ **Zero confiança implícita** em qualquer requisição

---

**Documento mantido por**: Claude (AI Assistant)
**Última atualização**: 2025-11-23
**Status**: 🚧 Implementação em andamento
