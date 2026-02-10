from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update

from fcontrol_api.cleanup.tasks.old_login_logs import run
from fcontrol_api.models.security.logs import UserActionLog
from tests.factories import UserActionLogFactory

pytestmark = pytest.mark.anyio


async def test_cleanup_removes_old_login_logs(session, users):
    user, _ = users
    old_date = datetime.now() - timedelta(days=60)

    log = UserActionLogFactory(
        user_id=user.id,
        action='login',
        resource='auth',
        resource_id=None,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    await session.execute(
        update(UserActionLog)
        .where(UserActionLog.id == log.id)
        .values(timestamp=old_date)
    )
    await session.commit()

    result = await run(session)

    assert result.status == 'success'
    assert result.rows_affected == 1
    assert result.task_name == 'cleanup_old_login_logs'

    remaining = await session.scalar(
        select(UserActionLog).where(UserActionLog.id == log.id)
    )
    assert remaining is None


async def test_cleanup_keeps_recent_login_logs(session, users):
    user, _ = users

    log = UserActionLogFactory(
        user_id=user.id,
        action='login',
        resource='auth',
        resource_id=None,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    log_id = log.id

    result = await run(session)

    assert result.status == 'skipped'

    remaining = await session.scalar(
        select(UserActionLog).where(UserActionLog.id == log_id)
    )
    assert remaining is not None


async def test_cleanup_with_no_old_logs(session, users):
    result = await run(session)

    assert result.task_name == 'cleanup_old_login_logs'
    assert result.status == 'skipped'
    assert result.rows_affected == 0
    assert result.details['reason'] == 'Nenhum log de login antigo'


async def test_cleanup_returns_error_on_db_failure(session, users):
    with patch.object(
        session,
        'execute',
        new_callable=AsyncMock,
        side_effect=RuntimeError('conexao perdida'),
    ):
        result = await run(session)

    assert result.task_name == 'cleanup_old_login_logs'
    assert result.status == 'error'
    assert result.rows_affected == 0
    assert 'conexao perdida' in result.errors[0]
    assert result.duration_seconds >= 0
