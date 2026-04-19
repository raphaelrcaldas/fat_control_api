import time
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.cleanup.models.cleanup_result import CleanupTaskResult
from fcontrol_api.models.security.auth import OAuth2AuthorizationCode

TASK_NAME = 'cleanup_expired_auth_codes'


async def run(session: AsyncSession) -> CleanupTaskResult:
    """Remove AuthCodes expirados que nunca foram trocados por token."""
    start = time.monotonic()
    now = datetime.now(timezone.utc)

    try:
        result = await session.execute(
            delete(OAuth2AuthorizationCode).where(
                OAuth2AuthorizationCode.expires_at < now
            )
        )

        if result.rowcount == 0:
            return CleanupTaskResult(
                task_name=TASK_NAME,
                status='skipped',
                duration_seconds=time.monotonic() - start,
                details={'reason': 'Nenhum código expirado'},
            )

        await session.commit()

        return CleanupTaskResult(
            task_name=TASK_NAME,
            status='success',
            rows_affected=result.rowcount,
            duration_seconds=time.monotonic() - start,
            details={'cutoff': now.isoformat()},
        )
    except Exception as e:
        await session.rollback()
        return CleanupTaskResult(
            task_name=TASK_NAME,
            status='error',
            duration_seconds=time.monotonic() - start,
            errors=[str(e)],
        )
