from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from fcontrol_api.settings import Settings

settings = Settings()

config = {
    'pool_pre_ping': True,
    'connect_args': {'command_timeout': 60},
    'echo': False,
}

if settings.ENV == 'production':
    config['poolclass'] = NullPool
else:
    config['pool_size'] = 5
    config['max_overflow'] = 5

engine = create_async_engine(settings.DATABASE_URL, **config)


async def get_session():
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
