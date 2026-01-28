"""
Fixtures para testes de Logs.
"""

import pytest

from tests.factories import UserActionLogFactory


@pytest.fixture
async def user_action_logs(session, users):
    """
    Cria logs de acoes para testes.

    Cria 5 logs com diferentes recursos, acoes e timestamps.

    Returns:
        list[UserActionLog]: Lista de logs criados
    """
    user, other_user = users

    logs = [
        # Log 1: user, create, users, agora
        UserActionLogFactory(
            user_id=user.id,
            action='create',
            resource='users',
            resource_id=100,
        ),
        # Log 2: user, update, trips, 1 dia atras
        UserActionLogFactory(
            user_id=user.id,
            action='update',
            resource='trips',
            resource_id=200,
        ),
        # Log 3: other_user, delete, quads, 2 dias atras
        UserActionLogFactory(
            user_id=other_user.id,
            action='delete',
            resource='quads',
            resource_id=300,
        ),
        # Log 4: user, read, indisp, 3 dias atras
        UserActionLogFactory(
            user_id=user.id,
            action='read',
            resource='indisp',
            resource_id=400,
        ),
        # Log 5: other_user, create, users, 4 dias atras
        UserActionLogFactory(
            user_id=other_user.id,
            action='create',
            resource='users',
            resource_id=500,
        ),
    ]

    session.add_all(logs)
    await session.commit()

    for log in logs:
        await session.refresh(log)

    return logs
