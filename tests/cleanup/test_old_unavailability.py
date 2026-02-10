from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from fcontrol_api.cleanup.tasks.old_unavailability import (
    cleanup_old_unavailability,
)
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.security.logs import UserActionLog
from tests.factories import IndispFactory, UserActionLogFactory

pytestmark = pytest.mark.anyio


async def test_cleanup_removes_old_indisps(session, users):
    user, other_user = users
    old_date = date.today() - timedelta(days=90)

    old_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=old_date - timedelta(days=5),
        date_end=old_date,
    )
    session.add(old_indisp)
    await session.commit()
    await session.refresh(old_indisp)
    old_id = old_indisp.id

    result = await cleanup_old_unavailability(session)

    assert result.status == 'success'
    assert result.rows_affected == 1

    remaining = await session.scalar(
        select(Indisp).where(Indisp.id == old_id)
    )
    assert remaining is None


async def test_cleanup_keeps_recent_indisps(session, users):
    user, other_user = users
    recent_date = date.today() - timedelta(days=10)

    recent_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=recent_date - timedelta(days=5),
        date_end=recent_date,
    )
    session.add(recent_indisp)
    await session.commit()
    await session.refresh(recent_indisp)
    recent_id = recent_indisp.id

    await cleanup_old_unavailability(session)

    remaining = await session.scalar(
        select(Indisp).where(Indisp.id == recent_id)
    )
    assert remaining is not None


async def test_cleanup_removes_related_logs(session, users):
    user, other_user = users
    old_date = date.today() - timedelta(days=90)

    old_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=old_date - timedelta(days=5),
        date_end=old_date,
    )
    session.add(old_indisp)
    await session.commit()
    await session.refresh(old_indisp)

    log = UserActionLogFactory(
        user_id=user.id,
        action='create',
        resource='indisp',
        resource_id=old_indisp.id,
    )
    session.add(log)
    await session.commit()

    result = await cleanup_old_unavailability(session)

    assert result.status == 'success'
    assert result.details['logs_deleted'] == 1

    remaining_logs = (
        await session.execute(
            select(UserActionLog).where(
                UserActionLog.resource == 'indisp',
                UserActionLog.resource_id == old_indisp.id,
            )
        )
    ).scalars().all()
    assert len(remaining_logs) == 0


async def test_cleanup_returns_result_with_metrics(session, users):
    user, other_user = users
    old_date = date.today() - timedelta(days=90)

    old_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=old_date - timedelta(days=5),
        date_end=old_date,
    )
    session.add(old_indisp)
    await session.commit()
    await session.refresh(old_indisp)

    result = await cleanup_old_unavailability(session)

    assert result.task_name == 'cleanup_old_unavailability'
    assert result.status == 'success'
    assert result.rows_affected >= 1
    assert result.duration_seconds >= 0
    assert result.errors == []
    assert 'ids_removed' in result.details
    assert 'logs_deleted' in result.details
    assert 'cutoff_date' in result.details


async def test_cleanup_with_no_old_indisps(session, users):
    result = await cleanup_old_unavailability(session)

    assert result.task_name == 'cleanup_old_unavailability'
    assert result.status == 'skipped'
    assert result.rows_affected == 0
    assert result.details['reason'] == 'Nenhuma indisponibilidade antiga'


async def test_cleanup_returns_error_on_db_failure(session, users):
    with patch.object(
        session,
        'execute',
        new_callable=AsyncMock,
        side_effect=RuntimeError('conexao perdida'),
    ):
        result = await cleanup_old_unavailability(session)

    assert result.task_name == 'cleanup_old_unavailability'
    assert result.status == 'error'
    assert result.rows_affected == 0
    assert 'conexao perdida' in result.errors[0]
    assert result.duration_seconds >= 0
