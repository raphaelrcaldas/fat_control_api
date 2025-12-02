# Refatoração: Base Única com Mixins para Schemas

## Objetivo

Migrar a arquitetura atual de **múltiplas bases declarativas** (uma por schema) para uma **base única com mixins**, eliminando a necessidade de consolidação manual de metadados e tornando o código mais Pythônico e manutenível.

---

## Situação Atual

### Estrutura Existente

```
fcontrol_api/models/
├── __init__.py              # Consolida metadados manualmente
├── public/
│   └── base.py              # Base sem schema (public é default)
├── security/
│   └── base.py              # Base com schema='security'
├── cegep/
│   └── base.py              # Base com schema='cegep'
└── nav/
    └── base.py              # Base com schema='nav'
```

### Problemas Identificados

1. **Consolidação Manual**: Loop verboso no `__init__.py` para unificar metadados
2. **Múltiplas Bases**: Confusão sobre qual base usar em novos modelos
3. **Repetição de Código**: Cada `base.py` tem código similar
4. **Complexidade Desnecessária**: Metadata separados que precisam ser mesclados

---

## Solução Proposta: Base Única + Mixins

### Nova Estrutura

```
fcontrol_api/models/
├── __init__.py              # Apenas exports
├── base.py                  # Base única para TODOS os modelos
├── mixins.py                # Mixins de schema
├── public/
│   └── users.py             # class User(PublicSchemaMixin, Base)
├── security/
│   └── auth.py              # class Auth(SecuritySchemaMixin, Base)
├── cegep/
│   └── diarias.py           # class Diaria(CegepSchemaMixin, Base)
└── nav/
    └── aerodromos.py        # class Aerodromo(NavSchemaMixin, Base)
```

---

## Plano de Implementação

### Etapa 1: Criar Arquivos Base

#### 1.1. Criar `fcontrol_api/models/base.py`

```python
"""Base declarativa única para todos os modelos do projeto."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

# Naming convention para constraints consistentes
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(MappedAsDataclass, DeclarativeBase):
    """Base única para todos os modelos do projeto.

    Subclasses serão convertidas em dataclasses automaticamente.
    Use os mixins de schema para definir o schema da tabela.
    """

    metadata = metadata
```

#### 1.2. Criar `fcontrol_api/models/mixins.py`

```python
"""Mixins para definir schemas de tabelas."""


class PublicSchemaMixin:
    """Mixin para tabelas do schema 'public'.

    Exemplo:
        class User(PublicSchemaMixin, Base):
            __tablename__ = 'users'
            # ...
    """

    __table_args__ = {"schema": "public"}


class SecuritySchemaMixin:
    """Mixin para tabelas do schema 'security'.

    Exemplo:
        class Auth(SecuritySchemaMixin, Base):
            __tablename__ = 'auth'
            # ...
    """

    __table_args__ = {"schema": "security"}


class CegepSchemaMixin:
    """Mixin para tabelas do schema 'cegep'.

    Exemplo:
        class Diaria(CegepSchemaMixin, Base):
            __tablename__ = 'diarias'
            # ...
    """

    __table_args__ = {"schema": "cegep"}


class NavSchemaMixin:
    """Mixin para tabelas do schema 'nav'.

    Exemplo:
        class Aerodromo(NavSchemaMixin, Base):
            __tablename__ = 'aerodromos'
            # ...
    """

    __table_args__ = {"schema": "nav"}
```

---

### Etapa 2: Atualizar Modelos Existentes

Para cada modelo, substitua a importação da base antiga pelo novo padrão:

#### Antes (exemplo com `nav/aerodromos.py`):

```python
from .base import Base

class Aerodromo(Base):
    __tablename__ = 'aerodromos'
    # ...
```

#### Depois:

```python
from fcontrol_api.models.base import Base
from fcontrol_api.models.mixins import NavSchemaMixin

class Aerodromo(NavSchemaMixin, Base):
    __tablename__ = 'aerodromos'
    # ...
```

#### Checklist de Modelos a Atualizar:

- [ ] **Schema Public**:
  - [ ] `public/users.py` → `PublicSchemaMixin`
  - [ ] `public/tripulantes.py` → `PublicSchemaMixin`
  - [ ] `public/posto_grad.py` → `PublicSchemaMixin`
  - [ ] `public/funcoes.py` → `PublicSchemaMixin`
  - [ ] `public/quads.py` → `PublicSchemaMixin`
  - [ ] `public/indisp.py` → `PublicSchemaMixin`
  - [ ] `public/estados_cidades.py` → `PublicSchemaMixin`

- [ ] **Schema Security**:
  - [ ] `security/auth.py` → `SecuritySchemaMixin`
  - [ ] `security/logs.py` → `SecuritySchemaMixin`
  - [ ] `security/resources.py` → `SecuritySchemaMixin`

- [ ] **Schema Cegep**:
  - [ ] `cegep/diarias.py` → `CegepSchemaMixin`
  - [ ] `cegep/missoes.py` → `CegepSchemaMixin`
  - [ ] `cegep/comiss.py` → `CegepSchemaMixin`
  - [ ] `cegep/dados_bancarios.py` → `CegepSchemaMixin`

- [ ] **Schema Nav**:
  - [ ] `nav/aerodromos.py` → `NavSchemaMixin`

---

### Etapa 3: Atualizar `fcontrol_api/models/__init__.py`

#### Antes (código atual):

```python
from sqlalchemy import MetaData

from .cegep.base import Base as BaseCegep
from .nav.base import Base as BaseNav
from .public.base import Base as BasePublic
from .security.base import Base as BaseSecurity

metadata = MetaData()
for m in [
    BasePublic.metadata,
    BaseSecurity.metadata,
    BaseCegep.metadata,
    BaseNav.metadata,
]:
    for t in m.tables.values():
        t.tometadata(metadata)
```

#### Depois (simplificado):

```python
"""Models do projeto FControl API."""

from .base import Base, metadata
from .mixins import (
    CegepSchemaMixin,
    NavSchemaMixin,
    PublicSchemaMixin,
    SecuritySchemaMixin,
)

# Importar todos os modelos para registrar no metadata
from .cegep import *  # noqa: F403
from .nav import *  # noqa: F403
from .public import *  # noqa: F403
from .security import *  # noqa: F403

__all__ = [
    "Base",
    "metadata",
    "PublicSchemaMixin",
    "SecuritySchemaMixin",
    "CegepSchemaMixin",
    "NavSchemaMixin",
]
```

---

### Etapa 4: Remover Bases Antigas

Após confirmar que tudo funciona, deletar os arquivos:

```bash
rm fcontrol_api/models/public/base.py
rm fcontrol_api/models/security/base.py
rm fcontrol_api/models/cegep/base.py
rm fcontrol_api/models/nav/base.py
```

---

### Etapa 5: Atualizar Imports nos `__init__.py` de Cada Schema

#### Exemplo: `fcontrol_api/models/nav/__init__.py`

```python
"""Models do schema nav."""

from .aerodromos import Aerodromo

__all__ = ["Aerodromo"]
```

Repetir para `public/__init__.py`, `security/__init__.py`, `cegep/__init__.py`.

---

### Etapa 6: Atualizar Alembic (se necessário)

Verificar se o `env.py` do Alembic está importando corretamente:

```python
# migrations/env.py
from fcontrol_api.models import metadata

target_metadata = metadata
```

---

### Etapa 7: Testes

#### 7.1. Verificar Metadata

```python
# Script de teste
from fcontrol_api.models import metadata

print(f"Total de tabelas: {len(metadata.tables)}")
for table_name, table in metadata.tables.items():
    print(f"  - {table_name} (schema: {table.schema})")
```

#### 7.2. Testar Migrações

```bash
# Gerar nova migração de teste
poetry run alembic revision --autogenerate -m "test_refactor"

# Revisar se não há mudanças inesperadas
# (deve mostrar "no changes detected" se tudo estiver correto)
```

#### 7.3. Rodar Testes Unitários

```bash
poetry run pytest tests/
```

---

## Vantagens da Nova Arquitetura

### Antes da Refatoração

❌ Loop manual para consolidar metadados
❌ Múltiplas bases causam confusão
❌ Código duplicado em cada `base.py`
❌ Difícil adicionar novos schemas

### Depois da Refatoração

✅ Um único `metadata` consolidado automaticamente
✅ Herança clara: `Mixin + Base`
✅ Código DRY (Don't Repeat Yourself)
✅ Fácil extensão: criar novo mixin se precisar
✅ Naming conventions para constraints consistentes

---

## Possíveis Extensões Futuras

### 1. Mixins Compostos

Se precisar de tabelas com múltiplos `__table_args__`:

```python
class TimestampMixin:
    """Adiciona created_at e updated_at."""

    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now(), onupdate=func.now()
    )


# Uso
class User(PublicSchemaMixin, TimestampMixin, Base):
    __tablename__ = 'users'
    # Herda schema='public' + timestamps
```

### 2. Schema Dinâmico

Se precisar de schemas configuráveis:

```python
from sqlalchemy.orm import declared_attr

class DynamicSchemaMixin:
    @declared_attr.directive
    def __table_args__(cls) -> dict:
        schema = os.getenv(f"{cls.__tablename__.upper()}_SCHEMA", "public")
        return {"schema": schema}
```

---

## Checklist Final

- [ ] Criar `fcontrol_api/models/base.py`
- [ ] Criar `fcontrol_api/models/mixins.py`
- [ ] Atualizar todos os modelos para usar novos imports
- [ ] Simplificar `fcontrol_api/models/__init__.py`
- [ ] Remover arquivos `base.py` antigos
- [ ] Atualizar `__init__.py` de cada schema
- [ ] Verificar configuração do Alembic
- [ ] Rodar script de verificação de metadata
- [ ] Gerar migração de teste
- [ ] Rodar testes unitários
- [ ] Commitar mudanças

---

## Notas de Segurança

- **Backup do banco**: Criar backup antes de rodar migrações
- **Ambiente de teste**: Testar primeiro em dev/staging
- **Reversão**: Manter branch antiga até validação completa

---

## Referências

- [SQLAlchemy Declarative Mixins](https://docs.sqlalchemy.org/en/20/orm/declarative_mixins.html)
- [SQLAlchemy Naming Conventions](https://docs.sqlalchemy.org/en/20/core/constraints.html#constraint-naming-conventions)
- [Python MRO (Method Resolution Order)](https://docs.python.org/3/glossary.html#term-method-resolution-order)

---

**Data de criação**: 2025-12-01
**Autor**: Claude Code
**Status**: Planejamento
