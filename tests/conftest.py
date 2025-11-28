import os
import pathlib
import sys

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

from tests.seed import ALL_SEED_OBJECTS

# Configure testcontainers to use Podman
os.environ['DOCKER_HOST'] = (
    f'unix:///run/user/{os.getuid()}/podman/podman.sock'
)
os.environ['TESTCONTAINERS_RYUK_DISABLED'] = 'true'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(scope='session')
def postgres_container():
    """Start PostgreSQL container for testing"""
    with PostgresContainer('postgres:16-alpine') as postgres:
        yield postgres


@pytest.fixture(scope='session')
def database_url(postgres_container):
    """Get database URL from container"""
    return postgres_container.get_connection_url()


@pytest.fixture(scope='session')
def run_migrations(database_url):
    """Run Alembic migrations on test database (once per session)"""
    # Get project root (where alembic.ini is)
    project_root = pathlib.Path(__file__).parent.parent
    alembic_ini = project_root / 'alembic.ini'
    migrations_dir = project_root / 'migrations'

    # Convert sync URL to async for Alembic
    async_database_url = database_url.replace('psycopg2', 'asyncpg')

    print(f'\n[TEST] Project root: {project_root}')
    print(f'[TEST] Alembic ini: {alembic_ini}')
    print(f'[TEST] Migrations dir: {migrations_dir}')
    print(f'[TEST] Database URL: {async_database_url}')

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option('sqlalchemy.url', async_database_url)
    alembic_cfg.set_main_option('script_location', str(migrations_dir))

    # Set Python path to include project root
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Run migrations to head (from empty database)
    print('[TEST] Running alembic upgrade head...')
    command.upgrade(alembic_cfg, 'head')
    print('[TEST] Migrations completed')


@pytest.fixture(scope='session')
def seed_data(database_url, run_migrations):
    """Load seed data that persists for all tests (runs once per session)"""
    print('[TEST] Loading seed data...')

    # Create sync engine for seed data
    engine = create_engine(database_url)

    with Session(engine) as session:
        # Adiciona todos os objetos de seed centralizados
        session.add_all(ALL_SEED_OBJECTS)
        session.commit()

    engine.dispose()
    print('[TEST] Seed data loaded successfully')


@pytest.fixture
async def session(database_url, run_migrations, seed_data):
    """Create database session with transaction rollback"""
    # Convert to async URL
    async_db_url = database_url.replace('psycopg2', 'asyncpg')

    engine = create_async_engine(async_db_url, echo=False)

    # Create a connection
    async with engine.connect() as connection:
        # Start a transaction
        transaction = await connection.begin()

        # Create a session bound to this connection
        session = AsyncSession(bind=connection, expire_on_commit=False)

        yield session

        # Rollback the transaction (discards all changes)
        await transaction.rollback()
        await session.close()

    await engine.dispose()
