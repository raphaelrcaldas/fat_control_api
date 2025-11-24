# Plano de Implementação: Sistema de Gerenciamento RBAC

**Projeto**: FControl API
**Data**: 2025-11-24
**Versão**: 1.0
**Autor**: Sistema de Planejamento

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Análise do Sistema Atual](#análise-do-sistema-atual)
3. [Objetivos](#objetivos)
4. [Arquitetura Proposta](#arquitetura-proposta)
5. [Implementação - Fase 1: Read-Only](#fase-1-read-only-endpoints)
6. [Implementação - Fase 2: Role-Permission Management](#fase-2-role-permission-management)
7. [Implementação - Fase 3: Full CRUD](#fase-3-full-crud-opcional)
8. [Schemas Pydantic](#schemas-pydantic)
9. [Segurança e Validações](#segurança-e-validações)
10. [Testes](#testes)
11. [Frontend (Opcional)](#frontend-opcional)
12. [Cronograma](#cronograma)
13. [Riscos e Mitigações](#riscos-e-mitigações)

---

## Visão Geral

### Contexto

O projeto FControl API possui um sistema RBAC completo implementado no banco de dados, mas **sem endpoints para gerenciamento**. Atualmente, a administração de roles e permissões requer acesso direto ao banco de dados via SQL.

### Problema

- ❌ Sem interface para criar/editar roles
- ❌ Sem forma de atribuir permissões a roles
- ❌ Impossível adicionar novos recursos/permissões sem SQL manual
- ❌ Dificuldade em auditar mudanças de permissões
- ❌ Operações sujeitas a erros humanos

### Solução

Criar endpoints REST para gerenciar todo o ciclo de vida do RBAC:
- Resources (recursos protegidos)
- Permissions (ações em recursos)
- Roles (perfis de usuário)
- Role-Permission associations (atribuição de permissões a roles)

---

## Análise do Sistema Atual

### Estrutura de Dados Existente

```
┌──────────────┐
│   Resources  │
│ - id         │
│ - name       │ (ex: "user", "mission", "payment")
│ - description│
└──────┬───────┘
       │ 1:N
       ▼
┌──────────────┐
│  Permissions │
│ - id         │
│ - resource_id│
│ - name       │ (ex: "create", "read", "update", "delete")
│ - description│
└──────┬───────┘
       │ N:M
       ▼
┌──────────────────┐      ┌──────────────┐
│ RolePermissions  │◄────►│    Roles     │
│ - id             │      │ - id         │
│ - role_id        │      │ - name       │ (ex: "admin", "operator")
│ - permission_id  │      │ - description│
└──────────────────┘      └──────┬───────┘
                                 │ N:M
                                 ▼
                          ┌──────────────┐
                          │  UserRole    │
                          │ - user_id    │
                          │ - role_id    │
                          └──────────────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │    User      │
                          └──────────────┘
```

### Modelos Existentes

**Localização**: `fcontrol_api/models/security/`

- ✅ `resources.py` - `Resources`
- ✅ `permissions.py` - `Permissions`
- ✅ `roles.py` - `Roles`
- ✅ `role_permissions.py` - `RolePermissions`
- ✅ `user_role.py` - `UserRole`

### Endpoints Existentes

**Router**: `fcontrol_api/routers/security.py`

| Endpoint | Método | Funcionalidade | Status |
|----------|--------|----------------|--------|
| `/security/roles` | GET | Listar todas as roles | ✅ |
| `/security/roles/users` | GET | Listar user-role assignments | ✅ |
| `/security/roles/users` | POST | Atribuir role a usuário | ✅ |
| `/security/roles/users` | PUT | Atualizar role de usuário | ✅ |
| `/security/roles/users` | DELETE | Remover role de usuário | ✅ |

### Funcionalidades de Segurança Existentes

**Localização**: `fcontrol_api/security.py`

```python
# Authentication
get_current_user(request, session) → User

# Authorization - Simple
require_admin(session, user) → User  # Hardcoded "admin" check

# Authorization - Fine-grained
permission_checker(resource: str, action: str, session, user) → User
```

**Uso atual**:
- Endpoints `/security/*` → `require_admin`
- Endpoint `/users` POST → `permission_checker('user', 'create')`
- Maioria dos endpoints → apenas `get_current_user` (sem authz)

### Service Layer Existente

**Localização**: `fcontrol_api/services/auth.py`

```python
async def get_user_roles(user_id: int, session: Session):
    """Retorna role e todas as permissions do usuário"""
    # Faz joins complexos para resolver: User → Role → Permissions → Resources
    return {
        'role': 'admin',
        'perms': [
            {'resource': 'user', 'name': 'create'},
            {'resource': 'user', 'name': 'read'},
            # ...
        ]
    }
```

---

## Objetivos

### Objetivo Primário

**Permitir gerenciamento completo do RBAC via API REST**, eliminando necessidade de acesso direto ao banco de dados.

### Objetivos Secundários

1. **Auditoria**: Registrar todas as mudanças de permissões no `SecurityLog`
2. **Self-Service**: Permitir que admins gerenciem permissões via UI futura
3. **Escalabilidade**: Facilitar adição de novos recursos/permissões conforme app cresce
4. **Segurança**: Prevenir self-lockout e mudanças acidentais críticas
5. **Conformidade**: Suportar roadmap Zero Trust (ZERO_TRUST_IMPLEMENTATION_PLAN.md)

### Métricas de Sucesso

- ✅ 100% das operações RBAC possíveis via API (sem SQL manual)
- ✅ Todas as mudanças auditadas no `SecurityLog`
- ✅ Zero incidentes de self-lockout em produção
- ✅ Redução de tempo para adicionar nova role: 5min (vs 30min SQL manual)
- ✅ Cobertura de testes ≥ 90% nos novos endpoints

---

## Arquitetura Proposta

### Princípios de Design

1. **RESTful**: Seguir convenções REST para recursos e operações
2. **Idempotência**: PUT/DELETE devem ser idempotentes
3. **Atomicidade**: Mudanças complexas em transações
4. **Auditabilidade**: Toda mudança gera log com before/after
5. **Fail-Safe**: Validações impedem estados inconsistentes
6. **Admin-Only**: Todos os endpoints requerem role `admin` (ou futura permission `security:manage`)

### Camadas da Aplicação

```
┌─────────────────────────────────────────────┐
│         Routers (API Layer)                 │
│  /security/resources, /roles, /permissions  │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│      Dependencies (Security Layer)          │
│  require_admin / permission_checker         │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│       Services (Business Logic)             │
│  rbac.py - Validações, cascata, audit       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│        Models (Data Layer)                  │
│  Resources, Permissions, Roles, etc         │
└─────────────────────────────────────────────┘
```

### Novos Componentes

#### 1. Service: `fcontrol_api/services/rbac.py` (NOVO)

Lógica de negócio para operações RBAC:
- Validações (prevent self-lockout, cascade checks)
- Audit logging
- Business rules (ex: sempre manter 1 admin)

#### 2. Schemas: `fcontrol_api/schemas/security.py` (NOVO/ATUALIZAR)

Pydantic schemas para request/response:
- `ResourceSchema`, `ResourceCreate`, `ResourceUpdate`
- `PermissionSchema`, `PermissionCreate`, `PermissionUpdate`
- `RoleDetailSchema` (role + suas permissions)
- `RolePermissionAssignSchema`

#### 3. Router: `fcontrol_api/routers/security.py` (ATUALIZAR)

Adicionar novos endpoints:
- `/security/resources` (CRUD)
- `/security/permissions` (CRUD)
- `/security/roles` (CRUD - atualizar existente)
- `/security/roles/{id}/permissions` (manage associations)

---

## Fase 1: Read-Only Endpoints

**Objetivo**: Dar visibilidade ao sistema RBAC existente sem risco de mudanças.

**Duração Estimada**: 2-3 horas

**Risco**: 🟢 Baixo (apenas leitura)

### 1.1. Schemas Pydantic

**Arquivo**: `fcontrol_api/schemas/security.py`

```python
from pydantic import BaseModel, ConfigDict

# Resources
class ResourceBase(BaseModel):
    name: str
    description: str

class ResourceSchema(ResourceBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# Permissions
class PermissionBase(BaseModel):
    resource_id: int
    name: str
    description: str

class PermissionSchema(PermissionBase):
    id: int
    resource: ResourceSchema
    model_config = ConfigDict(from_attributes=True)

class PermissionDetailSchema(BaseModel):
    """Permission com nome do resource (para listagens)"""
    id: int
    resource: str  # resource.name
    action: str    # permission.name
    description: str
    model_config = ConfigDict(from_attributes=True)

# Roles
class RoleSchema(BaseModel):
    id: int
    name: str
    description: str
    model_config = ConfigDict(from_attributes=True)

class RoleDetailSchema(RoleSchema):
    """Role com suas permissions"""
    permissions: list[PermissionDetailSchema]
```

### 1.2. Endpoints Read-Only

**Arquivo**: `fcontrol_api/routers/security.py`

#### Endpoint 1: Listar Resources

```python
@router.get('/resources', response_model=list[ResourceSchema])
async def list_resources(
    session: Session,
    _: User = Depends(require_admin)
):
    """
    Lista todos os recursos protegidos no sistema.

    Requer: role admin
    """
    stmt = select(Resources).order_by(Resources.name)
    resources = await session.scalars(stmt)
    return list(resources)
```

**Teste manual**:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/security/resources
```

**Resposta esperada**:
```json
[
  {"id": 1, "name": "user", "description": "Gestão de usuários"},
  {"id": 2, "name": "mission", "description": "Gestão de missões"},
  {"id": 3, "name": "payment", "description": "Gestão de pagamentos"}
]
```

---

#### Endpoint 2: Listar Permissions

```python
@router.get('/permissions', response_model=list[PermissionDetailSchema])
async def list_permissions(
    session: Session,
    resource_name: str | None = None,  # Filtro opcional
    _: User = Depends(require_admin)
):
    """
    Lista todas as permissões disponíveis.

    Query params:
        resource_name: Filtrar por recurso (ex: "user")

    Requer: role admin
    """
    stmt = (
        select(Permissions)
        .options(joinedload(Permissions.resource))
        .order_by(Permissions.resource_id, Permissions.name)
    )

    if resource_name:
        stmt = stmt.join(Resources).where(Resources.name == resource_name)

    permissions = await session.scalars(stmt)

    return [
        PermissionDetailSchema(
            id=p.id,
            resource=p.resource.name,
            action=p.name,
            description=p.description
        )
        for p in permissions
    ]
```

**Teste manual**:
```bash
# Todas as permissions
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/security/permissions

# Apenas permissions do resource "user"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/security/permissions?resource_name=user
```

---

#### Endpoint 3: Obter Role com Permissions

```python
@router.get('/roles/{role_id}', response_model=RoleDetailSchema)
async def get_role_detail(
    role_id: int,
    session: Session,
    _: User = Depends(require_admin)
):
    """
    Obtém detalhes de uma role incluindo todas as suas permissões.

    Requer: role admin
    """
    stmt = (
        select(Roles)
        .where(Roles.id == role_id)
        .options(
            joinedload(Roles.permissions)
            .joinedload(RolePermissions.permission)
            .joinedload(Permissions.resource)
        )
    )

    role = await session.scalar(stmt)

    if not role:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Role não encontrada'
        )

    return RoleDetailSchema(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=[
            PermissionDetailSchema(
                id=rp.permission.id,
                resource=rp.permission.resource.name,
                action=rp.permission.name,
                description=rp.permission.description
            )
            for rp in role.permissions
        ]
    )
```

**Teste manual**:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/security/roles/1
```

**Resposta esperada**:
```json
{
  "id": 1,
  "name": "admin",
  "description": "Administrador do sistema",
  "permissions": [
    {"id": 1, "resource": "user", "action": "create", "description": "Criar usuários"},
    {"id": 2, "resource": "user", "action": "read", "description": "Visualizar usuários"},
    {"id": 3, "resource": "user", "action": "update", "description": "Editar usuários"},
    {"id": 4, "resource": "user", "action": "delete", "description": "Deletar usuários"}
  ]
}
```

---

#### Endpoint 4: Listar Roles (atualizar existente)

```python
@router.get('/roles', response_model=list[RoleSchema])
async def list_roles(
    session: Session,
    _: User = Depends(require_admin)
):
    """
    Lista todas as roles disponíveis (sem details de permissions).

    Use GET /roles/{id} para ver permissions de uma role específica.

    Requer: role admin
    """
    stmt = select(Roles).order_by(Roles.name)
    roles = await session.scalars(stmt)
    return list(roles)
```

---

### 1.3. Checklist Fase 1

- [ ] Criar arquivo `fcontrol_api/schemas/security.py`
- [ ] Adicionar schemas: `ResourceSchema`, `PermissionDetailSchema`, `RoleDetailSchema`
- [ ] Adicionar endpoint `GET /security/resources`
- [ ] Adicionar endpoint `GET /security/permissions`
- [ ] Adicionar endpoint `GET /security/roles/{role_id}` (detalhado)
- [ ] Atualizar endpoint `GET /security/roles` (usar novo schema)
- [ ] Testar todos os endpoints manualmente (curl/Postman)
- [ ] Validar que apenas admin tem acesso
- [ ] Commit: `feat(security): add read-only RBAC management endpoints`

---

## Fase 2: Role-Permission Management

**Objetivo**: Permitir criar/editar roles e atribuir/remover permissões.

**Duração Estimada**: 4-6 horas

**Risco**: 🟡 Médio (mudanças de estado, precisa validações)

### 2.1. Service Layer (Business Logic)

**Arquivo**: `fcontrol_api/services/rbac.py` (NOVO)

```python
from http import HTTPStatus
from sqlalchemy import select, func, delete
from sqlalchemy.orm import joinedload
from fastapi import HTTPException

from fcontrol_api.models import Roles, Permissions, RolePermissions, UserRole, User
from fcontrol_api.services.logs import log_user_action


async def validate_role_exists(role_id: int, session) -> Roles:
    """Valida que role existe, retorna a instância ou HTTPException 404"""
    role = await session.get(Roles, role_id)
    if not role:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f'Role {role_id} não encontrada'
        )
    return role


async def validate_permission_exists(permission_id: int, session) -> Permissions:
    """Valida que permission existe, retorna a instância ou HTTPException 404"""
    permission = await session.get(
        Permissions,
        permission_id,
        options=[joinedload(Permissions.resource)]
    )
    if not permission:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f'Permission {permission_id} não encontrada'
        )
    return permission


async def check_role_has_users(role_id: int, session) -> int:
    """Retorna quantidade de usuários com essa role"""
    stmt = select(func.count(UserRole.id)).where(UserRole.role_id == role_id)
    count = await session.scalar(stmt)
    return count


async def prevent_self_admin_removal(role: Roles, admin_user_id: int, session) -> None:
    """
    Impede que admin remova sua própria role admin.
    Raises HTTPException 400 se tentar.
    """
    if role.name.lower() != 'admin':
        return  # Não é role admin, pode prosseguir

    # Verificar se o usuário atual tem essa role
    stmt = select(UserRole).where(
        UserRole.user_id == admin_user_id,
        UserRole.role_id == role.id
    )
    user_role = await session.scalar(stmt)

    if user_role:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Você não pode modificar/deletar sua própria role admin'
        )


async def ensure_at_least_one_admin(session) -> None:
    """
    Verifica se existe pelo menos 1 usuário com role admin.
    Raises HTTPException 400 se não houver.
    """
    stmt = (
        select(func.count(UserRole.id))
        .join(Roles)
        .where(Roles.name.ilike('admin'))  # Case-insensitive
    )
    admin_count = await session.scalar(stmt)

    if admin_count == 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Operação negada: deve existir pelo menos 1 administrador no sistema'
        )


async def add_permission_to_role_safe(
    role_id: int,
    permission_id: int,
    admin_user_id: int,
    session
) -> dict:
    """
    Adiciona uma permission a uma role com validações.

    Returns:
        dict com detalhes da operação

    Raises:
        HTTPException se validações falharem
    """
    # Validar existência
    role = await validate_role_exists(role_id, session)
    permission = await validate_permission_exists(permission_id, session)

    # Verificar se já existe
    stmt = select(RolePermissions).where(
        RolePermissions.role_id == role_id,
        RolePermissions.permission_id == permission_id
    )
    existing = await session.scalar(stmt)

    if existing:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f'Permission {permission.resource.name}.{permission.name} já está atribuída à role {role.name}'
        )

    # Adicionar
    role_permission = RolePermissions(
        role_id=role_id,
        permission_id=permission_id
    )
    session.add(role_permission)

    # Auditar
    await log_user_action(
        session=session,
        user_id=admin_user_id,
        action='add_permission_to_role',
        resource='role',
        resource_id=role_id,
        before_state=None,
        after_state={
            'role': role.name,
            'permission_id': permission_id,
            'permission': f'{permission.resource.name}.{permission.name}'
        }
    )

    await session.commit()

    return {
        'role': role.name,
        'permission': f'{permission.resource.name}.{permission.name}',
        'detail': f'Permission {permission.resource.name}.{permission.name} adicionada à role {role.name}'
    }


async def remove_permission_from_role_safe(
    role_id: int,
    permission_id: int,
    admin_user_id: int,
    session
) -> dict:
    """
    Remove uma permission de uma role com validações.
    """
    role = await validate_role_exists(role_id, session)
    permission = await validate_permission_exists(permission_id, session)

    # Verificar se existe
    stmt = select(RolePermissions).where(
        RolePermissions.role_id == role_id,
        RolePermissions.permission_id == permission_id
    )
    role_permission = await session.scalar(stmt)

    if not role_permission:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f'Role {role.name} não possui permission {permission.resource.name}.{permission.name}'
        )

    # Auditar (antes de deletar)
    await log_user_action(
        session=session,
        user_id=admin_user_id,
        action='remove_permission_from_role',
        resource='role',
        resource_id=role_id,
        before_state={
            'role': role.name,
            'permission': f'{permission.resource.name}.{permission.name}'
        },
        after_state=None
    )

    # Remover
    await session.delete(role_permission)
    await session.commit()

    return {
        'detail': f'Permission {permission.resource.name}.{permission.name} removida da role {role.name}'
    }


async def delete_role_safe(role_id: int, admin_user_id: int, session) -> dict:
    """
    Deleta uma role com validações de segurança.
    """
    role = await validate_role_exists(role_id, session)

    # Prevenir self-lockout
    await prevent_self_admin_removal(role, admin_user_id, session)

    # Verificar se tem usuários
    user_count = await check_role_has_users(role_id, session)
    if user_count > 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f'Role {role.name} está atribuída a {user_count} usuário(s). Reatribua antes de deletar.'
        )

    # Auditar
    await log_user_action(
        session=session,
        user_id=admin_user_id,
        action='delete_role',
        resource='role',
        resource_id=role_id,
        before_state={'name': role.name, 'description': role.description},
        after_state=None
    )

    # Deletar role_permissions associadas
    await session.execute(
        delete(RolePermissions).where(RolePermissions.role_id == role_id)
    )

    # Deletar role
    await session.delete(role)
    await session.commit()

    return {'detail': f'Role {role.name} deletada com sucesso'}
```

---

### 2.2. Schemas Adicionais

**Arquivo**: `fcontrol_api/schemas/security.py` (adicionar)

```python
# Role Create/Update
class RoleCreate(BaseModel):
    name: str
    description: str

class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

# Role-Permission Assignment
class RolePermissionAssign(BaseModel):
    """Schema para atribuir permission a role"""
    permission_id: int

class RolePermissionRemove(BaseModel):
    """Schema para remover permission de role"""
    permission_id: int
```

---

### 2.3. Endpoints de Modificação

**Arquivo**: `fcontrol_api/routers/security.py` (adicionar)

#### Endpoint 5: Criar Role

```python
from fcontrol_api.services.rbac import (
    add_permission_to_role_safe,
    remove_permission_from_role_safe,
    delete_role_safe
)

@router.post('/roles', response_model=RoleSchema, status_code=HTTPStatus.CREATED)
async def create_role(
    role_data: RoleCreate,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Cria uma nova role.

    Body:
        name: Nome da role (ex: "operator")
        description: Descrição (ex: "Operador do sistema")

    Requer: role admin
    """
    # Verificar se já existe
    stmt = select(Roles).where(Roles.name.ilike(role_data.name))
    existing = await session.scalar(stmt)

    if existing:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f'Role {role_data.name} já existe'
        )

    # Criar
    role = Roles(
        name=role_data.name,
        description=role_data.description
    )
    session.add(role)

    # Auditar
    await log_user_action(
        session=session,
        user_id=admin.id,
        action='create_role',
        resource='role',
        resource_id=None,  # Ainda não tem ID
        before_state=None,
        after_state={'name': role.name, 'description': role.description}
    )

    await session.commit()
    await session.refresh(role)

    return role
```

---

#### Endpoint 6: Atualizar Role

```python
@router.put('/roles/{role_id}', response_model=RoleSchema)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Atualiza nome/descrição de uma role.

    Requer: role admin
    """
    from fcontrol_api.services.rbac import validate_role_exists, prevent_self_admin_removal

    role = await validate_role_exists(role_id, session)

    # Prevenir modificação da própria role admin
    await prevent_self_admin_removal(role, admin.id, session)

    # Guardar estado anterior
    before_state = {'name': role.name, 'description': role.description}

    # Atualizar campos
    if role_data.name is not None:
        # Verificar se novo nome já existe
        stmt = select(Roles).where(
            Roles.name.ilike(role_data.name),
            Roles.id != role_id
        )
        existing = await session.scalar(stmt)
        if existing:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f'Role {role_data.name} já existe'
            )
        role.name = role_data.name

    if role_data.description is not None:
        role.description = role_data.description

    # Auditar
    await log_user_action(
        session=session,
        user_id=admin.id,
        action='update_role',
        resource='role',
        resource_id=role_id,
        before_state=before_state,
        after_state={'name': role.name, 'description': role.description}
    )

    await session.commit()
    await session.refresh(role)

    return role
```

---

#### Endpoint 7: Deletar Role

```python
@router.delete('/roles/{role_id}', status_code=HTTPStatus.NO_CONTENT)
async def delete_role(
    role_id: int,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Deleta uma role.

    Validações:
    - Não pode deletar role com usuários atribuídos
    - Não pode deletar sua própria role admin
    - Deve sempre existir pelo menos 1 admin

    Requer: role admin
    """
    from fcontrol_api.services.rbac import delete_role_safe

    await delete_role_safe(role_id, admin.id, session)
    return None  # 204 No Content
```

---

#### Endpoint 8: Adicionar Permission a Role

```python
@router.post('/roles/{role_id}/permissions')
async def add_permission_to_role(
    role_id: int,
    data: RolePermissionAssign,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Adiciona uma permission a uma role.

    Body:
        permission_id: ID da permission a adicionar

    Requer: role admin
    """
    from fcontrol_api.services.rbac import add_permission_to_role_safe

    result = await add_permission_to_role_safe(
        role_id=role_id,
        permission_id=data.permission_id,
        admin_user_id=admin.id,
        session=session
    )

    return result
```

---

#### Endpoint 9: Remover Permission de Role

```python
@router.delete('/roles/{role_id}/permissions/{permission_id}')
async def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Remove uma permission de uma role.

    Requer: role admin
    """
    from fcontrol_api.services.rbac import remove_permission_from_role_safe

    result = await remove_permission_from_role_safe(
        role_id=role_id,
        permission_id=permission_id,
        admin_user_id=admin.id,
        session=session
    )

    return result
```

---

### 2.4. Checklist Fase 2

- [ ] Criar arquivo `fcontrol_api/services/rbac.py`
- [ ] Implementar funções de validação e segurança
- [ ] Implementar `add_permission_to_role_safe()`
- [ ] Implementar `remove_permission_from_role_safe()`
- [ ] Implementar `delete_role_safe()`
- [ ] Adicionar schemas `RoleCreate`, `RoleUpdate`, `RolePermissionAssign`
- [ ] Adicionar endpoint `POST /security/roles`
- [ ] Adicionar endpoint `PUT /security/roles/{role_id}`
- [ ] Adicionar endpoint `DELETE /security/roles/{role_id}`
- [ ] Adicionar endpoint `POST /security/roles/{role_id}/permissions`
- [ ] Adicionar endpoint `DELETE /security/roles/{role_id}/permissions/{permission_id}`
- [ ] Testar cenário: criar role, adicionar permissions
- [ ] Testar cenário: tentar deletar role com usuários (deve falhar)
- [ ] Testar cenário: admin tentar remover própria role (deve falhar)
- [ ] Testar cenário: atualizar role, validar audit log
- [ ] Commit: `feat(security): add role-permission management endpoints`

---

## Fase 3: Full CRUD (Opcional)

**Objetivo**: Permitir criar novos Resources e Permissions conforme aplicação escala.

**Duração Estimada**: 3-4 horas

**Risco**: 🟡 Médio (menos usado, pode ser postergado)

**Quando implementar**: Quando precisar adicionar um novo módulo/feature que requer novos resources (ex: "report", "dashboard", "integration").

### 3.1. Schemas Adicionais

```python
# Resource CRUD
class ResourceCreate(BaseModel):
    name: str  # Ex: "report"
    description: str

class ResourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

# Permission CRUD
class PermissionCreate(BaseModel):
    resource_id: int
    name: str  # Ex: "export"
    description: str

class PermissionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
```

### 3.2. Endpoints Resources

```python
@router.post('/resources', response_model=ResourceSchema, status_code=HTTPStatus.CREATED)
async def create_resource(
    resource_data: ResourceCreate,
    session: Session,
    admin: User = Depends(require_admin)
):
    """Cria um novo resource (ex: "report", "integration")"""
    # Verificar duplicata
    stmt = select(Resources).where(Resources.name.ilike(resource_data.name))
    existing = await session.scalar(stmt)
    if existing:
        raise HTTPException(400, f'Resource {resource_data.name} já existe')

    resource = Resources(**resource_data.model_dump())
    session.add(resource)

    await log_user_action(session, admin.id, 'create_resource', 'resource', None,
                         after_state=resource_data.model_dump())

    await session.commit()
    await session.refresh(resource)
    return resource


@router.put('/resources/{resource_id}', response_model=ResourceSchema)
async def update_resource(
    resource_id: int,
    resource_data: ResourceUpdate,
    session: Session,
    admin: User = Depends(require_admin)
):
    """Atualiza resource existente"""
    resource = await session.get(Resources, resource_id)
    if not resource:
        raise HTTPException(404, 'Resource não encontrado')

    before = {'name': resource.name, 'description': resource.description}

    if resource_data.name:
        resource.name = resource_data.name
    if resource_data.description:
        resource.description = resource_data.description

    await log_user_action(session, admin.id, 'update_resource', 'resource', resource_id,
                         before_state=before, after_state={'name': resource.name, 'description': resource.description})

    await session.commit()
    return resource


@router.delete('/resources/{resource_id}', status_code=HTTPStatus.NO_CONTENT)
async def delete_resource(
    resource_id: int,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Deleta um resource.

    ⚠️  WARNING: Deletará em cascata todas as permissions e role_permissions associadas!
    """
    resource = await session.get(Resources, resource_id)
    if not resource:
        raise HTTPException(404, 'Resource não encontrado')

    # Verificar quantas permissions serão afetadas
    stmt = select(func.count(Permissions.id)).where(Permissions.resource_id == resource_id)
    perm_count = await session.scalar(stmt)

    if perm_count > 0:
        # Forçar confirmação via header especial
        # (ou implementar soft delete)
        raise HTTPException(
            400,
            f'Resource {resource.name} possui {perm_count} permissions. Operação perigosa - não implementada por segurança.'
        )

    await log_user_action(session, admin.id, 'delete_resource', 'resource', resource_id,
                         before_state={'name': resource.name}, after_state=None)

    await session.delete(resource)
    await session.commit()
    return None
```

### 3.3. Endpoints Permissions

```python
@router.post('/permissions', response_model=PermissionSchema, status_code=HTTPStatus.CREATED)
async def create_permission(
    perm_data: PermissionCreate,
    session: Session,
    admin: User = Depends(require_admin)
):
    """Cria uma nova permission para um resource"""
    # Validar resource existe
    resource = await session.get(Resources, perm_data.resource_id)
    if not resource:
        raise HTTPException(404, 'Resource não encontrado')

    # Verificar duplicata
    stmt = select(Permissions).where(
        Permissions.resource_id == perm_data.resource_id,
        Permissions.name.ilike(perm_data.name)
    )
    existing = await session.scalar(stmt)
    if existing:
        raise HTTPException(400, f'Permission {resource.name}.{perm_data.name} já existe')

    permission = Permissions(**perm_data.model_dump())
    session.add(permission)

    await log_user_action(session, admin.id, 'create_permission', 'permission', None,
                         after_state=perm_data.model_dump())

    await session.commit()
    await session.refresh(permission)
    return permission


@router.put('/permissions/{permission_id}', response_model=PermissionSchema)
async def update_permission(
    permission_id: int,
    perm_data: PermissionUpdate,
    session: Session,
    admin: User = Depends(require_admin)
):
    """Atualiza permission existente"""
    permission = await session.get(Permissions, permission_id)
    if not permission:
        raise HTTPException(404, 'Permission não encontrada')

    before = {'name': permission.name, 'description': permission.description}

    if perm_data.name:
        permission.name = perm_data.name
    if perm_data.description:
        permission.description = perm_data.description

    await log_user_action(session, admin.id, 'update_permission', 'permission', permission_id,
                         before_state=before, after_state={'name': permission.name, 'description': permission.description})

    await session.commit()
    return permission


@router.delete('/permissions/{permission_id}', status_code=HTTPStatus.NO_CONTENT)
async def delete_permission(
    permission_id: int,
    session: Session,
    admin: User = Depends(require_admin)
):
    """
    Deleta uma permission.

    ⚠️  WARNING: Removerá permission de todas as roles!
    """
    permission = await session.get(Permissions, permission_id, options=[joinedload(Permissions.resource)])
    if not permission:
        raise HTTPException(404, 'Permission não encontrada')

    # Verificar quantas roles usam
    stmt = select(func.count(RolePermissions.id)).where(RolePermissions.permission_id == permission_id)
    role_count = await session.scalar(stmt)

    if role_count > 0:
        raise HTTPException(
            400,
            f'Permission {permission.resource.name}.{permission.name} está em uso por {role_count} role(s). '
            'Remova das roles antes de deletar.'
        )

    await log_user_action(session, admin.id, 'delete_permission', 'permission', permission_id,
                         before_state={'name': permission.name, 'resource': permission.resource.name}, after_state=None)

    await session.delete(permission)
    await session.commit()
    return None
```

### 3.4. Checklist Fase 3

- [ ] Adicionar schemas `ResourceCreate/Update`, `PermissionCreate/Update`
- [ ] Implementar endpoints CRUD para `/security/resources`
- [ ] Implementar endpoints CRUD para `/security/permissions`
- [ ] Adicionar validações de cascata (prevent delete se em uso)
- [ ] Testar criação de novo resource + permissions + atribuição a role
- [ ] Validar audit logs
- [ ] Commit: `feat(security): add full CRUD for resources and permissions`

---

## Schemas Pydantic

### Arquivo Completo: `fcontrol_api/schemas/security.py`

```python
"""
Schemas Pydantic para sistema RBAC.

Estrutura:
- Resources: Recursos protegidos (ex: "user", "mission")
- Permissions: Ações em recursos (ex: "create", "read")
- Roles: Perfis de usuário (ex: "admin", "operator")
- RolePermissions: Associação many-to-many
"""
from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# RESOURCES
# ============================================================================

class ResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Nome do recurso (ex: 'user')")
    description: str = Field(..., min_length=1, max_length=200)


class ResourceCreate(ResourceBase):
    """Schema para criar novo resource"""
    pass


class ResourceUpdate(BaseModel):
    """Schema para atualizar resource (campos opcionais)"""
    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, min_length=1, max_length=200)


class ResourceSchema(ResourceBase):
    """Schema de resposta com ID"""
    id: int
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PERMISSIONS
# ============================================================================

class PermissionBase(BaseModel):
    resource_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=50, description="Nome da ação (ex: 'create')")
    description: str = Field(..., min_length=1, max_length=200)


class PermissionCreate(PermissionBase):
    """Schema para criar nova permission"""
    pass


class PermissionUpdate(BaseModel):
    """Schema para atualizar permission"""
    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, min_length=1, max_length=200)


class PermissionSchema(PermissionBase):
    """Schema de resposta básico"""
    id: int
    model_config = ConfigDict(from_attributes=True)


class PermissionDetailSchema(BaseModel):
    """Permission com informações do resource (para listagens)"""
    id: int
    resource: str = Field(..., description="Nome do resource")
    action: str = Field(..., description="Nome da permission")
    description: str

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# ROLES
# ============================================================================

class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Nome da role (ex: 'admin')")
    description: str = Field(..., min_length=1, max_length=200)


class RoleCreate(RoleBase):
    """Schema para criar nova role"""
    pass


class RoleUpdate(BaseModel):
    """Schema para atualizar role"""
    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, min_length=1, max_length=200)


class RoleSchema(RoleBase):
    """Schema de resposta básico"""
    id: int
    model_config = ConfigDict(from_attributes=True)


class RoleDetailSchema(RoleSchema):
    """Role com todas as suas permissions"""
    permissions: list[PermissionDetailSchema] = Field(default_factory=list)


# ============================================================================
# ROLE-PERMISSION ASSIGNMENT
# ============================================================================

class RolePermissionAssign(BaseModel):
    """Schema para atribuir permission a role"""
    permission_id: int = Field(..., gt=0, description="ID da permission a adicionar")


class RolePermissionRemove(BaseModel):
    """Schema para remover permission de role"""
    permission_id: int = Field(..., gt=0, description="ID da permission a remover")


# ============================================================================
# USER-ROLE ASSIGNMENT (já existe, mas documentar aqui)
# ============================================================================

class UserRoleSchema(BaseModel):
    """Schema para atribuir role a usuário (já existente)"""
    user_id: int
    role_id: int
```

---

## Segurança e Validações

### Checklist de Segurança

#### 1. **Autenticação/Autorização**
- [ ] Todos os endpoints protegidos por `require_admin`
- [ ] Considerar criar permission `security:manage` em vez de hardcoded admin
- [ ] JWT válido requerido (middleware existente)

#### 2. **Prevent Self-Lockout**
- [ ] Implementado: `prevent_self_admin_removal()`
- [ ] Admin não pode deletar sua própria role
- [ ] Admin não pode remover todas as permissions da sua role
- [ ] Sempre manter pelo menos 1 admin no sistema

#### 3. **Validação de Dados**
- [ ] Pydantic schemas com validação (Field constraints)
- [ ] Checks de duplicata (nome de role/resource/permission único)
- [ ] Foreign keys validados (resource_id, permission_id, role_id)
- [ ] Case-insensitive checks onde aplicável (`.ilike()`)

#### 4. **Integridade de Dados**
- [ ] Transações para operações multi-step
- [ ] Prevent delete se role tem usuários
- [ ] Prevent delete se resource/permission em uso
- [ ] Cascata consciente (avisar antes de operações destrutivas)

#### 5. **Auditoria**
- [ ] Todas as mutações logadas no `SecurityLog`
- [ ] Before/After state capturado
- [ ] User ID do admin que fez a mudança
- [ ] Timestamp automático (model padrão)

#### 6. **Rate Limiting** (Futuro)
- [ ] Considerar rate limiting em endpoints de modificação
- [ ] Prevenir brute force de IDs (ex: tentar deletar todas as roles)

---

## Testes

### 1. Testes Unitários (pytest)

**Arquivo**: `tests/test_rbac_management.py`

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models import Resources, Permissions, Roles, RolePermissions, UserRole


@pytest.mark.asyncio
class TestResourcesEndpoints:
    async def test_list_resources_as_admin(self, client: AsyncClient, admin_token: str):
        response = await client.get(
            '/security/resources',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_resources_as_non_admin_forbidden(self, client: AsyncClient, user_token: str):
        response = await client.get(
            '/security/resources',
            headers={'Authorization': f'Bearer {user_token}'}
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestRoleManagement:
    async def test_create_role(self, client: AsyncClient, admin_token: str):
        response = await client.post(
            '/security/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': 'test_operator', 'description': 'Test operator role'}
        )
        assert response.status_code == 201
        data = response.json()
        assert data['name'] == 'test_operator'
        assert 'id' in data

    async def test_create_duplicate_role_fails(self, client: AsyncClient, admin_token: str):
        # Criar primeira
        await client.post(
            '/security/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': 'duplicate', 'description': 'First'}
        )

        # Tentar duplicata
        response = await client.post(
            '/security/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': 'duplicate', 'description': 'Second'}
        )
        assert response.status_code == 400
        assert 'já existe' in response.json()['detail']

    async def test_delete_role_with_users_fails(
        self,
        client: AsyncClient,
        admin_token: str,
        session: AsyncSession
    ):
        # Criar role e atribuir a usuário
        role = Roles(name='temp_role', description='Temporary')
        session.add(role)
        await session.commit()
        await session.refresh(role)

        user_role = UserRole(user_id=1, role_id=role.id)
        session.add(user_role)
        await session.commit()

        # Tentar deletar
        response = await client.delete(
            f'/security/roles/{role.id}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert response.status_code == 400
        assert 'atribuída a' in response.json()['detail']

    async def test_admin_cannot_delete_own_role(
        self,
        client: AsyncClient,
        admin_token: str,
        admin_user_id: int,
        session: AsyncSession
    ):
        # Obter role admin
        stmt = select(Roles).where(Roles.name.ilike('admin'))
        admin_role = await session.scalar(stmt)

        response = await client.delete(
            f'/security/roles/{admin_role.id}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert response.status_code == 400
        assert 'própria role admin' in response.json()['detail']


@pytest.mark.asyncio
class TestRolePermissionManagement:
    async def test_add_permission_to_role(
        self,
        client: AsyncClient,
        admin_token: str,
        session: AsyncSession
    ):
        # Setup: criar role e permission
        role = Roles(name='test_role', description='Test')
        resource = Resources(name='test_resource', description='Test')
        session.add_all([role, resource])
        await session.commit()
        await session.refresh(role)
        await session.refresh(resource)

        permission = Permissions(resource_id=resource.id, name='read', description='Read')
        session.add(permission)
        await session.commit()
        await session.refresh(permission)

        # Adicionar permission a role
        response = await client.post(
            f'/security/roles/{role.id}/permissions',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'permission_id': permission.id}
        )
        assert response.status_code == 200
        assert 'adicionada' in response.json()['detail']

        # Verificar no banco
        stmt = select(RolePermissions).where(
            RolePermissions.role_id == role.id,
            RolePermissions.permission_id == permission.id
        )
        rp = await session.scalar(stmt)
        assert rp is not None

    async def test_add_duplicate_permission_fails(
        self,
        client: AsyncClient,
        admin_token: str,
        session: AsyncSession
    ):
        # Setup
        role = Roles(name='test_role2', description='Test')
        resource = Resources(name='test_resource2', description='Test')
        session.add_all([role, resource])
        await session.commit()
        await session.refresh(role)
        await session.refresh(resource)

        permission = Permissions(resource_id=resource.id, name='write', description='Write')
        session.add(permission)
        await session.commit()
        await session.refresh(permission)

        # Adicionar primeira vez
        await client.post(
            f'/security/roles/{role.id}/permissions',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'permission_id': permission.id}
        )

        # Tentar adicionar novamente
        response = await client.post(
            f'/security/roles/{role.id}/permissions',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'permission_id': permission.id}
        )
        assert response.status_code == 400
        assert 'já está atribuída' in response.json()['detail']

    async def test_remove_permission_from_role(
        self,
        client: AsyncClient,
        admin_token: str,
        session: AsyncSession
    ):
        # Setup
        role = Roles(name='test_role3', description='Test')
        resource = Resources(name='test_resource3', description='Test')
        session.add_all([role, resource])
        await session.commit()
        await session.refresh(role)
        await session.refresh(resource)

        permission = Permissions(resource_id=resource.id, name='delete', description='Delete')
        session.add(permission)
        await session.commit()
        await session.refresh(permission)

        role_permission = RolePermissions(role_id=role.id, permission_id=permission.id)
        session.add(role_permission)
        await session.commit()

        # Remover
        response = await client.delete(
            f'/security/roles/{role.id}/permissions/{permission.id}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert response.status_code == 200
        assert 'removida' in response.json()['detail']

        # Verificar remoção no banco
        stmt = select(RolePermissions).where(
            RolePermissions.role_id == role.id,
            RolePermissions.permission_id == permission.id
        )
        rp = await session.scalar(stmt)
        assert rp is None


@pytest.mark.asyncio
class TestAuditLogging:
    async def test_role_creation_is_logged(
        self,
        client: AsyncClient,
        admin_token: str,
        admin_user_id: int,
        session: AsyncSession
    ):
        # Criar role
        response = await client.post(
            '/security/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': 'audit_test_role', 'description': 'For audit test'}
        )
        assert response.status_code == 201

        # Verificar log
        from fcontrol_api.models.security.logs import SecurityLog
        stmt = select(SecurityLog).where(
            SecurityLog.user_id == admin_user_id,
            SecurityLog.action == 'create_role'
        ).order_by(SecurityLog.timestamp.desc())
        log = await session.scalar(stmt)

        assert log is not None
        assert log.resource == 'role'
        assert 'audit_test_role' in str(log.after_state)
```

### 2. Testes de Integração

```python
@pytest.mark.asyncio
class TestRBACWorkflow:
    async def test_full_role_lifecycle(
        self,
        client: AsyncClient,
        admin_token: str,
        session: AsyncSession
    ):
        """
        Teste end-to-end:
        1. Criar resource
        2. Criar permissions
        3. Criar role
        4. Atribuir permissions a role
        5. Verificar role detail
        6. Remover permission
        7. Deletar role
        """
        # 1. Criar resource
        resource_response = await client.post(
            '/security/resources',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': 'workflow_resource', 'description': 'Test'}
        )
        assert resource_response.status_code == 201
        resource_id = resource_response.json()['id']

        # 2. Criar permissions
        perm_ids = []
        for action in ['create', 'read', 'update']:
            perm_response = await client.post(
                '/security/permissions',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={
                    'resource_id': resource_id,
                    'name': action,
                    'description': f'{action.capitalize()} workflow resource'
                }
            )
            assert perm_response.status_code == 201
            perm_ids.append(perm_response.json()['id'])

        # 3. Criar role
        role_response = await client.post(
            '/security/roles',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'name': 'workflow_role', 'description': 'Test workflow role'}
        )
        assert role_response.status_code == 201
        role_id = role_response.json()['id']

        # 4. Atribuir permissions
        for perm_id in perm_ids:
            assign_response = await client.post(
                f'/security/roles/{role_id}/permissions',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'permission_id': perm_id}
            )
            assert assign_response.status_code == 200

        # 5. Verificar role detail
        detail_response = await client.get(
            f'/security/roles/{role_id}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert detail_response.status_code == 200
        role_data = detail_response.json()
        assert len(role_data['permissions']) == 3

        # 6. Remover uma permission
        remove_response = await client.delete(
            f'/security/roles/{role_id}/permissions/{perm_ids[0]}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert remove_response.status_code == 200

        # Verificar remoção
        detail_response2 = await client.get(
            f'/security/roles/{role_id}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert len(detail_response2.json()['permissions']) == 2

        # 7. Deletar role
        delete_response = await client.delete(
            f'/security/roles/{role_id}',
            headers={'Authorization': f'Bearer {admin_token}'}
        )
        assert delete_response.status_code == 204
```

---

## Frontend (Opcional)

### Wireframe Simples

```
┌─────────────────────────────────────────────────────────────────┐
│  RBAC Management                                    [Admin Only] │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Roles ────────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  ☑ Admin         [15 permissions]  [Edit] [Delete]         │ │
│  │  ☑ Operator      [ 8 permissions]  [Edit] [Delete]         │ │
│  │  ☐ Viewer        [ 3 permissions]  [Edit] [Delete]         │ │
│  │  ☐ Finance Mgr   [ 6 permissions]  [Edit] [Delete]         │ │
│  │                                                              │ │
│  │  [+ Create New Role]                                        │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Permissions for Role: "Operator" ──────────────────────────┐ │
│  │                                                              │ │
│  │  Resource: user                                             │ │
│  │    ☑ create   ☑ read   ☑ update   ☐ delete                │ │
│  │                                                              │ │
│  │  Resource: mission                                          │ │
│  │    ☑ create   ☑ read   ☑ update   ☐ delete                │ │
│  │                                                              │ │
│  │  Resource: payment                                          │ │
│  │    ☐ create   ☑ read   ☐ update   ☐ delete                │ │
│  │                                                              │ │
│  │  [+ Add Permission]                                         │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Available Resources ────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  • user       (4 permissions)                               │ │
│  │  • mission    (4 permissions)                               │ │
│  │  • payment    (4 permissions)                               │ │
│  │  • report     (3 permissions)                               │ │
│  │                                                              │ │
│  │  [+ Create New Resource]                                    │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes React (Exemplo)

```typescript
// RoleManagement.tsx
import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface Role {
  id: number;
  name: string;
  description: string;
}

interface Permission {
  id: number;
  resource: string;
  action: string;
  description: string;
}

interface RoleDetail extends Role {
  permissions: Permission[];
}

export function RoleManagement() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedRole, setSelectedRole] = useState<RoleDetail | null>(null);
  const [allPermissions, setAllPermissions] = useState<Permission[]>([]);

  useEffect(() => {
    loadRoles();
    loadAllPermissions();
  }, []);

  async function loadRoles() {
    const response = await api.get('/security/roles');
    setRoles(response.data);
  }

  async function loadAllPermissions() {
    const response = await api.get('/security/permissions');
    setAllPermissions(response.data);
  }

  async function selectRole(roleId: number) {
    const response = await api.get(`/security/roles/${roleId}`);
    setSelectedRole(response.data);
  }

  async function addPermissionToRole(permissionId: number) {
    if (!selectedRole) return;

    await api.post(`/security/roles/${selectedRole.id}/permissions`, {
      permission_id: permissionId
    });

    // Reload
    selectRole(selectedRole.id);
  }

  async function removePermissionFromRole(permissionId: number) {
    if (!selectedRole) return;

    await api.delete(`/security/roles/${selectedRole.id}/permissions/${permissionId}`);

    // Reload
    selectRole(selectedRole.id);
  }

  return (
    <div className="rbac-management">
      <div className="roles-list">
        <h2>Roles</h2>
        {roles.map(role => (
          <div
            key={role.id}
            className={selectedRole?.id === role.id ? 'active' : ''}
            onClick={() => selectRole(role.id)}
          >
            {role.name}
          </div>
        ))}
      </div>

      <div className="role-permissions">
        {selectedRole && (
          <>
            <h2>Permissions for {selectedRole.name}</h2>

            <div className="current-permissions">
              {selectedRole.permissions.map(perm => (
                <div key={perm.id} className="permission-item">
                  {perm.resource}.{perm.action}
                  <button onClick={() => removePermissionFromRole(perm.id)}>
                    Remove
                  </button>
                </div>
              ))}
            </div>

            <h3>Add Permission</h3>
            <select onChange={(e) => addPermissionToRole(Number(e.target.value))}>
              <option value="">Select permission...</option>
              {allPermissions
                .filter(p => !selectedRole.permissions.find(sp => sp.id === p.id))
                .map(perm => (
                  <option key={perm.id} value={perm.id}>
                    {perm.resource}.{perm.action}
                  </option>
                ))
              }
            </select>
          </>
        )}
      </div>
    </div>
  );
}
```

---

## Cronograma

### Semana 1: Fase 1 - Read-Only

| Dia | Tarefa | Duração | Responsável |
|-----|--------|---------|-------------|
| D1  | Criar schemas Pydantic (Resources, Permissions, Roles) | 1h | Dev |
| D1  | Implementar endpoints read-only (GET /resources, /permissions, /roles/{id}) | 2h | Dev |
| D1  | Testes manuais (curl/Postman) | 30min | Dev |
| D2  | Code review + ajustes | 1h | Team |
| D2  | Deploy em staging | 30min | DevOps |
| D2  | Validação em staging | 30min | QA |

**Entrega**: Endpoints de leitura funcionando, visibilidade completa do RBAC.

---

### Semana 2: Fase 2 - Role-Permission Management

| Dia | Tarefa | Duração | Responsável |
|-----|--------|---------|-------------|
| D3  | Criar service layer (rbac.py) com validações | 2h | Dev |
| D3  | Implementar endpoints: POST/PUT/DELETE /roles | 2h | Dev |
| D4  | Implementar endpoints: POST/DELETE /roles/{id}/permissions | 2h | Dev |
| D4  | Adicionar audit logging em todas as operações | 1h | Dev |
| D5  | Testes unitários (pytest) | 3h | Dev |
| D5  | Testes de integração (workflow completo) | 2h | Dev |
| D6  | Code review + refactoring | 2h | Team |
| D6  | Testes manuais end-to-end | 1h | QA |
| D7  | Deploy em staging | 30min | DevOps |
| D7  | Validação completa em staging | 2h | QA |

**Entrega**: Sistema completo de gerenciamento de roles e permissions.

---

### Semana 3 (Opcional): Frontend

| Dia | Tarefa | Duração | Responsável |
|-----|--------|---------|-------------|
| D8-D10 | Criar componentes React (RoleManagement, PermissionMatrix) | 8h | Frontend Dev |
| D11 | Integração com API | 3h | Frontend Dev |
| D12 | Testes E2E (Playwright/Cypress) | 3h | QA |
| D12 | Deploy | 1h | DevOps |

**Entrega**: Interface administrativa para gerenciamento RBAC.

---

### Semana 4+ (Futuro): Fase 3 - Full CRUD

| Tarefa | Duração | Quando |
|--------|---------|--------|
| Endpoints CRUD /resources | 2h | Quando precisar adicionar novo módulo |
| Endpoints CRUD /permissions | 2h | Quando precisar adicionar novo módulo |
| Validações de cascata | 2h | Antes de usar em produção |
| Testes | 3h | Sempre |

**Entrega**: Capacidade de adicionar novos recursos/permissões sem SQL manual.

---

## Riscos e Mitigações

### Risco 1: Self-Lockout (Admin remove própria role)

**Probabilidade**: Média
**Impacto**: Alto (sistema inacessível)

**Mitigação**:
- ✅ Validação `prevent_self_admin_removal()` implementada
- ✅ Sempre manter pelo menos 1 admin no sistema
- ✅ UI avisar antes de operações perigosas
- 🔄 Plano B: Script de recuperação via SQL direto

---

### Risco 2: Cascata Não Intencional (Deletar resource usado)

**Probabilidade**: Média
**Impacto**: Alto (usuários perdem acesso)

**Mitigação**:
- ✅ Checks antes de delete (count de permissions/roles afetadas)
- ✅ Retornar erro se resource/permission em uso
- ✅ Forçar remoção explícita antes de deletar
- 🔄 Considerar soft-delete em vez de hard-delete

---

### Risco 3: Inconsistência de Dados (Transação falha no meio)

**Probabilidade**: Baixa
**Impacto**: Médio

**Mitigação**:
- ✅ Usar transações SQLAlchemy (`async with session.begin()`)
- ✅ Rollback automático em caso de erro
- ✅ Testes de integração cobrem cenários de falha

---

### Risco 4: Auditoria Incompleta (Log não criado)

**Probabilidade**: Baixa
**Impacto**: Médio (conformidade)

**Mitigação**:
- ✅ Audit log dentro da mesma transação
- ✅ Se log falhar, operação faz rollback
- ✅ Testes validam presença de logs
- 🔄 Alertas de monitoring se logs param de ser criados

---

### Risco 5: Performance (Muitos JOINs)

**Probabilidade**: Baixa (RBAC tem poucos registros)
**Impacto**: Baixo

**Mitigação**:
- ✅ Eager loading (`joinedload`) para evitar N+1
- ✅ Índices em FKs (migrations já têm)
- 🔄 Cache de permissions do usuário (se necessário no futuro)

---

### Risco 6: Adoção Baixa (Usuários continuam usando SQL)

**Probabilidade**: Média
**Impacto**: Médio

**Mitigação**:
- ✅ Documentar API (OpenAPI/Swagger automático)
- ✅ Criar UI amigável (Fase 3)
- ✅ Treinamento da equipe
- 🔄 Restringir acesso direto ao banco em produção

---

## Apêndices

### A. Estrutura de Arquivos

```
fcontrol_api/
├── models/
│   └── security/
│       ├── resources.py          [Existente]
│       ├── permissions.py        [Existente]
│       ├── roles.py              [Existente]
│       ├── role_permissions.py   [Existente]
│       └── logs.py               [Existente]
│
├── schemas/
│   └── security.py               [NOVO - Fase 1]
│
├── services/
│   ├── auth.py                   [Existente]
│   ├── rbac.py                   [NOVO - Fase 2]
│   └── logs.py                   [Existente]
│
├── routers/
│   └── security.py               [ATUALIZAR - Fases 1-3]
│
└── security.py                   [Existente - usar dependencies]

tests/
├── test_rbac_read.py             [NOVO - Fase 1]
├── test_rbac_management.py       [NOVO - Fase 2]
└── test_rbac_full_crud.py        [NOVO - Fase 3]
```

---

### B. Resumo de Endpoints

#### Fase 1: Read-Only
- `GET /security/resources` - Listar resources
- `GET /security/permissions` - Listar permissions (filtro opcional por resource)
- `GET /security/roles` - Listar roles (básico)
- `GET /security/roles/{id}` - Obter role com permissions

#### Fase 2: Role-Permission Management
- `POST /security/roles` - Criar role
- `PUT /security/roles/{id}` - Atualizar role
- `DELETE /security/roles/{id}` - Deletar role
- `POST /security/roles/{id}/permissions` - Adicionar permission a role
- `DELETE /security/roles/{id}/permissions/{perm_id}` - Remover permission de role

#### Fase 3: Full CRUD (Opcional)
- `POST /security/resources` - Criar resource
- `PUT /security/resources/{id}` - Atualizar resource
- `DELETE /security/resources/{id}` - Deletar resource
- `POST /security/permissions` - Criar permission
- `PUT /security/permissions/{id}` - Atualizar permission
- `DELETE /security/permissions/{id}` - Deletar permission

**Total**: 15 endpoints

---

### C. Checklist de Deploy

**Pre-Deploy**:
- [ ] Todos os testes passando (pytest coverage ≥ 90%)
- [ ] Code review aprovado
- [ ] Migrations aplicadas (se houver alterações de schema)
- [ ] Documentação atualizada (OpenAPI)
- [ ] Variáveis de ambiente configuradas (se novas)

**Deploy**:
- [ ] Backup do banco de dados
- [ ] Deploy em staging
- [ ] Smoke tests em staging
- [ ] Validação de audit logs em staging
- [ ] Deploy em produção (horário de baixo tráfego)
- [ ] Smoke tests em produção

**Post-Deploy**:
- [ ] Monitoring ativo (erros 4xx/5xx)
- [ ] Verificar logs de auditoria estão sendo criados
- [ ] Comunicar equipe sobre novos endpoints
- [ ] Agendar treinamento (se UI foi deployada)

---

### D. Referências

- **Documentação Oficial**:
  - FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
  - SQLAlchemy Async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

- **Boas Práticas RBAC**:
  - NIST RBAC: https://csrc.nist.gov/projects/role-based-access-control
  - OWASP Authorization: https://owasp.org/www-community/Access_Control

- **Projeto FControl**:
  - Zero Trust Plan: `ZERO_TRUST_IMPLEMENTATION_PLAN.md`
  - Models: `fcontrol_api/models/security/`
  - Current Security: `fcontrol_api/security.py`

---

## Conclusão

Este plano fornece um roadmap completo para implementar gerenciamento RBAC no FControl API. A abordagem faseada permite:

1. **Fase 1**: Visibilidade rápida (low-risk)
2. **Fase 2**: Funcionalidade completa de gerenciamento (high-value)
3. **Fase 3**: Escalabilidade futura (nice-to-have)

**Próximos Passos Imediatos**:
1. Revisar e aprovar este plano com a equipe
2. Criar branch `feature/rbac-management`
3. Iniciar Fase 1 (duração: 2-3 horas)
4. Validar em staging antes de prosseguir para Fase 2

**Estimativa Total**:
- Fase 1: 3h (essencial)
- Fase 2: 14h (essencial)
- Fase 3: 9h (opcional)
- **Total Core**: ~17 horas (2-3 dias úteis)

---

**Documento criado**: 2025-11-24
**Última atualização**: 2025-11-24
**Status**: Pronto para implementação
