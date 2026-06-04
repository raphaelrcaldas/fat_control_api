import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.cleanup.models.cleanup_result import CleanupTaskResult
from fcontrol_api.models.security.logs import UserActionLog

TASK_NAME = 'cleanup_old_login_logs'
DESCRIPTION = 'Logs de login com mais de 30 dias'


async def count(session: AsyncSession, days_threshold: int = 30) -> int:
    cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=days_threshold
    )
    result = await session.execute(
        select(func.count())
        .select_from(UserActionLog)
        .where(
            UserActionLog.action == 'login',
            UserActionLog.resource == 'auth',
            UserActionLog.timestamp < cutoff_date,
        )
    )
    return result.scalar() or 0


async def run(
    session: AsyncSession,
    days_threshold: int = 30,
) -> CleanupTaskResult:
    """Remove logs de login antigos (action='login', resource='auth')."""
    start = time.monotonic()
    # Usar UTC naive para compatibilidade com a coluna timestamp
    cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=days_threshold
    )

    try:
        delete_result = await session.execute(
            delete(UserActionLog).where(
                UserActionLog.action == 'login',
                UserActionLog.resource == 'auth',
                UserActionLog.timestamp < cutoff_date,
            )
        )

        if delete_result.rowcount == 0:
            return CleanupTaskResult(
                task_name=TASK_NAME,
                status='skipped',
                duration_seconds=time.monotonic() - start,
                details={'reason': 'Nenhum log de login antigo'},
            )

        await session.commit()

        return CleanupTaskResult(
            task_name=TASK_NAME,
            status='success',
            rows_affected=delete_result.rowcount,
            duration_seconds=time.monotonic() - start,
            details={
                'cutoff_date': cutoff_date.isoformat(),
            },
        )
    except Exception as e:
        await session.rollback()
        return CleanupTaskResult(
            task_name=TASK_NAME,
            status='error',
            duration_seconds=time.monotonic() - start,
            errors=[str(e)],
        )
