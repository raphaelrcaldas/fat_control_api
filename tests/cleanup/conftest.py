import pytest

from fcontrol_api.security import get_password_hash
from tests.factories import UserFactory


@pytest.fixture
def anyio_backend():
    return 'asyncio'


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

    return (user, other_user)
