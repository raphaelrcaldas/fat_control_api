import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import fcontrol_api.models.aeromedica
import fcontrol_api.models.cegep
import fcontrol_api.models.estatistica
import fcontrol_api.models.instrucao
import fcontrol_api.models.inteligencia
import fcontrol_api.models.nav
import fcontrol_api.models.shared
import fcontrol_api.models.security
import fcontrol_api.models.seg_voo
from fcontrol_api.models.aeromedica.base import Base as BaseAeromedica
from fcontrol_api.models.cegep.base import Base as BaseCegep
from fcontrol_api.models.estatistica.base import Base as BaseStats
from fcontrol_api.models.instrucao.base import Base as BaseInstrucao
from fcontrol_api.models.inteligencia.base import Base as BaseInteligencia
from fcontrol_api.models.nav.base import Base as BaseNav
from fcontrol_api.models.shared.base import Base as BasePublic
from fcontrol_api.models.security.base import Base as BaseSecurity
from fcontrol_api.models.seg_voo.base import Base as BaseSegVoo
from fcontrol_api.settings import Settings

config = context.config
# Only set DATABASE_URL from Settings if not already configured (for tests)
if not config.get_main_option('sqlalchemy.url'):
    config.set_main_option('sqlalchemy.url', Settings().DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

metadata = MetaData()
for m in [
    BasePublic.metadata,
    BaseSecurity.metadata,
    BaseCegep.metadata,
    BaseNav.metadata,
    BaseStats.metadata,
    BaseAeromedica.metadata,
    BaseSegVoo.metadata,
    BaseInstrucao.metadata,
    BaseInteligencia.metadata,
]:
    for t in m.tables.values():
        t.tometadata(metadata)

target_metadata = metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
