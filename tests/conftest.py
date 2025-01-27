import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fcontrol_api.app import app
from fcontrol_api.database import get_session
from fcontrol_api.models import table_registry
from fcontrol_api.security import get_password_hash
from tests.factories import FuncFactory, QuadFactory, TripFactory, UserFactory


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def client(session):
    def get_session_override():
        return session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://127.0.0.1:8000/'
    ) as client:
        app.dependency_overrides[get_session] = get_session_override

        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def session():
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(table_registry.metadata.create_all)

    session = AsyncSession(engine)
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
async def users(session):
    password = 'testtest'

    user = UserFactory(password=get_password_hash(password))
    other_user = UserFactory()

    db_users = [user, other_user]

    session.add_all(db_users)
    await session.commit()

    for instance in db_users:
        await session.refresh(instance)

    user.clean_password = password

    return (user, other_user)


@pytest.fixture
async def trips(session, users):
    (user, other_user) = users

    trip = TripFactory(user_id=user.id)
    other_trip = TripFactory(user_id=other_user.id)

    db_trips = [trip, other_trip]

    session.add_all(db_trips)
    await session.commit()

    for instance in db_trips:
        await session.refresh(instance)

    return (trip, other_trip)


@pytest.fixture
async def funcao(session, trip):
    func = FuncFactory(trip_id=trip.id)

    session.add(func)
    await session.commit()
    await session.refresh(func)

    return func


@pytest.fixture
async def quad(session, trip):
    quad = QuadFactory(trip_id=trip.id)

    session.add(quad)
    await session.commit()
    await session.refresh(quad)

    return quad
