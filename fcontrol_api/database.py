from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from fcontrol_api.settings import Settings

engine = create_async_engine(Settings().DATABASE_URL)  # type: ignore


async def get_session():
    async with AsyncSession(engine) as session:
        yield session
