import importlib
import logging
import pkgutil

from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.cleanup import tasks as tasks_package
from fcontrol_api.cleanup.models.cleanup_result import CleanupTaskResult

logger = logging.getLogger(__name__)

ALLOWED_TASKS = {'old_login_logs', 'old_unavailability'}


async def run_all_tasks(
    session: AsyncSession,
) -> list[CleanupTaskResult]:
    """Descobre e executa todas as cleanup tasks permitidas."""
    results: list[CleanupTaskResult] = []

    for module_info in pkgutil.iter_modules(tasks_package.__path__):
        if module_info.name not in ALLOWED_TASKS:
            logger.warning(
                'Modulo inesperado ignorado: %s', module_info.name
            )
            continue

        module = importlib.import_module(
            f'fcontrol_api.cleanup.tasks.{module_info.name}'
        )

        run_fn = getattr(module, 'run', None)
        if run_fn is None:
            logger.warning(
                'Modulo %s sem funcao run, ignorado',
                module_info.name,
            )
            continue

        result = await run_fn(session)
        results.append(result)

    return results


def log_report(results: list[CleanupTaskResult]) -> None:
    """Loga relatorio consolidado das cleanup tasks."""
    separator = '=' * 60
    dash = '-' * 60
    header = (
        f'{"Task":<35} {"Status":<10} '
        f'{"Rows":<8} {"Duration":<10}'
    )

    lines = [
        '',
        separator,
        'CLEANUP REPORT',
        separator,
        header,
        dash,
    ]

    for r in results:
        lines.append(
            f'{r.task_name:<35} {r.status:<10} '
            f'{r.rows_affected:<8} {r.duration_seconds:.2f}s'
        )
        for err in r.errors:
            lines.append(f'  ERROR: {err}')

    total = len(results)
    success = sum(1 for r in results if r.status == 'success')
    skipped = sum(1 for r in results if r.status == 'skipped')
    errors = sum(1 for r in results if r.status == 'error')

    lines.append(separator)
    lines.append(
        f'Total: {total} | Success: {success} '
        f'| Skipped: {skipped} | Errors: {errors}'
    )
    lines.append(separator)

    logger.info('\n'.join(lines))
