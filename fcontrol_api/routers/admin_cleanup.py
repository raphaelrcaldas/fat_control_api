from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.cleanup.runner import preview_all_tasks, run_all_tasks
from fcontrol_api.database import get_session
from fcontrol_api.schemas.cleanup import (
    CleanupPreviewResponse,
    CleanupRunResponse,
    CleanupTaskPreview,
    CleanupTaskResultOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import require_system_admin
from fcontrol_api.utils.responses import success_response

router = APIRouter(
    prefix='/admin/cleanup',
    tags=['Admin - Limpeza'],
    dependencies=[Depends(require_system_admin)],
)


@router.get('/preview', response_model=ApiResponse[CleanupPreviewResponse])
async def preview_cleanup(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CleanupPreviewResponse]:
    """Retorna a contagem de registros candidatos para limpeza, sem executar."""
    previews = await preview_all_tasks(session)
    tasks = [CleanupTaskPreview(**p) for p in previews]
    total = sum(t.count for t in tasks)
    return success_response(
        data=CleanupPreviewResponse(tasks=tasks, total_records=total)
    )


@router.post('/run', response_model=ApiResponse[CleanupRunResponse])
async def run_cleanup(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CleanupRunResponse]:
    """Executa todas as cleanup tasks e retorna o relatório completo."""
    results = await run_all_tasks(session)
    tasks_out = [
        CleanupTaskResultOut(
            task_name=r.task_name,
            status=r.status,
            rows_affected=r.rows_affected,
            duration_seconds=r.duration_seconds,
            errors=r.errors,
            details=r.details,
        )
        for r in results
    ]
    total_deleted = sum(t.rows_affected for t in tasks_out)
    return success_response(
        data=CleanupRunResponse(
            tasks=tasks_out,
            total_deleted=total_deleted,
            executed_at=datetime.now().isoformat(),
        )
    )
