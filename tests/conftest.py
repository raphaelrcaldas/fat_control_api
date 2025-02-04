import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fcontrol_api.app import app
from fcontrol_api.database import get_session
from fcontrol_api.models.public.models import PostoGrad, table_registry
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
async def posto_table(session):
    data_table = [
        {
            'ant': 1,
            'short': 'tb',
            'mid': 'ten brig',
            'long': 'tenente-brigadeiro',
            'soldo': 13471,
            'circulo': 'of_gen',
        },
        {
            'ant': 2,
            'short': 'mb',
            'mid': 'maj brig',
            'long': 'major-brigadeiro',
            'soldo': 12912,
            'circulo': 'of_gen',
        },
        {
            'ant': 3,
            'short': 'br',
            'mid': 'brig',
            'long': 'brigadeiro',
            'soldo': 12490,
            'circulo': 'of_gen',
        },
        {
            'ant': 4,
            'short': 'cl',
            'mid': 'cel',
            'long': 'coronel',
            'soldo': 11451,
            'circulo': 'of_sup',
        },
        {
            'ant': 5,
            'short': 'tc',
            'mid': 'ten cel',
            'long': 'tenente-coronel',
            'soldo': 11250,
            'circulo': 'of_sup',
        },
        {
            'ant': 6,
            'short': 'mj',
            'mid': 'maj',
            'long': 'major',
            'soldo': 11088,
            'circulo': 'of_sup',
        },
        {
            'ant': 7,
            'short': 'cp',
            'mid': 'cap',
            'long': 'capitão',
            'soldo': 9135,
            'circulo': 'of_int',
        },
        {
            'ant': 8,
            'short': '1t',
            'mid': '1º ten',
            'long': 'primeiro tenente',
            'soldo': 8245,
            'circulo': 'of_sub',
        },
        {
            'ant': 9,
            'short': '2t',
            'mid': '2º ten',
            'long': 'segundo tenente',
            'soldo': 7490,
            'circulo': 'of_sub',
        },
        {
            'ant': 10,
            'short': 'as',
            'mid': 'asp',
            'long': 'aspirante',
            'soldo': 6993,
            'circulo': 'of_sub',
        },
        {
            'ant': 11,
            'short': 'so',
            'mid': 'sub of',
            'long': 'suboficial',
            'soldo': 6169,
            'circulo': 'grad',
        },
        {
            'ant': 12,
            'short': '1s',
            'mid': '1º sgt',
            'long': 'primeiro sargento',
            'soldo': 5483,
            'circulo': 'grad',
        },
        {
            'ant': 13,
            'short': '2s',
            'mid': '2º sgt',
            'long': 'segundo sargento',
            'soldo': 4770,
            'circulo': 'grad',
        },
        {
            'ant': 14,
            'short': '3s',
            'mid': '3º sgt',
            'long': 'terceiro sargento',
            'soldo': 3825,
            'circulo': 'grad',
        },
        {
            'ant': 15,
            'short': 'cb',
            'mid': 'cabo',
            'long': 'cabo',
            'soldo': 2627,
            'circulo': 'praça',
        },
        {
            'ant': 16,
            'short': 's1',
            'mid': 's1',
            'long': 'soldado primeira classe',
            'soldo': 1856,
            'circulo': 'praça',
        },
        {
            'ant': 17,
            'short': 's2',
            'mid': 's2',
            'long': 'soldado segunda classe',
            'soldo': 1560,
            'circulo': 'praça',
        },
    ]

    postos = [PostoGrad(**i) for i in data_table]

    session.add_all(postos)
    await session.commit()


@pytest.fixture
async def users(session, posto_table):
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
