import time
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.cleanup.models.cleanup_result import CleanupTaskResult
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.security.logs import UserActionLog

TASK_NAME = 'cleanup_old_unavailability'


async def run(
    session: AsyncSession,
    days_threshold: int = 60,
) -> CleanupTaskResult:
    """Remove indisponibilidades com date_end anterior ao threshold."""
    start = time.monotonic()
    cutoff_date = date.today() - timedelta(days=days_threshold)

    try:
        query = select(Indisp.id).where(
            Indisp.date_end < cutoff_date
        )
        result = await session.execute(query)
        ids_to_delete = [row[0] for row in result.all()]

        if not ids_to_delete:
            return CleanupTaskResult(
                task_name=TASK_NAME,
                status='skipped',
                duration_seconds=time.monotonic() - start,
                details={'reason': 'Nenhuma indisponibilidade antiga'},
            )

        logs_result = await session.execute(
            delete(UserActionLog).where(
                UserActionLog.resource == 'indisp',
                UserActionLog.resource_id.in_(ids_to_delete),
            )
        )
        logs_deleted = logs_result.rowcount

        await session.execute(
            delete(Indisp).where(Indisp.id.in_(ids_to_delete))
        )

        await session.commit()

        return CleanupTaskResult(
            task_name=TASK_NAME,
            status='success',
            rows_affected=len(ids_to_delete),
            duration_seconds=time.monotonic() - start,
            details={
                'ids_removed': ids_to_delete,
                'logs_deleted': logs_deleted,
                'cutoff_date': str(cutoff_date),
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


# Alias para compatibilidade com scripts standalone
cleanup_old_unavailability = run
