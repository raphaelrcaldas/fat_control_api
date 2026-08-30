"""Poda das notificações in-app já encerradas.

Só sai o que teve desfecho: direta LIDA (`read_at`) e tarefa RESOLVIDA
(`resolved_at`). Pendente nunca é apagada por idade — notificação sem
desfecho ainda é trabalho a fazer, e sumir com ela seria perder a
demanda em silêncio.

O corte usa a MESMA coluna do desfecho (não `created_at`): o que importa
é há quanto tempo o assunto foi encerrado.
"""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.cleanup.models.cleanup_result import CleanupTaskResult
from fcontrol_api.models.shared.notificacao import Notificacao

TASK_NAME = 'cleanup_old_notificacoes'
DESCRIPTION = 'Notificações lidas/resolvidas com mais de 90 dias'


def _cutoff(days_threshold: int) -> datetime:
    """Corte timezone-aware.

    `read_at`/`resolved_at` são `DateTime(timezone=True)`: comparar com
    naive daria erro no asyncpg em vez de filtrar.
    """
    return datetime.now(timezone.utc) - timedelta(days=days_threshold)


def _condicao(cutoff_date: datetime):
    """Predicado dos candidatos — o mesmo no `count` e no `run`.

    Recebe o corte pronto (em vez de recalculá-lo) para o valor relatado
    em `details` ser exatamente o aplicado no DELETE.
    """
    return or_(
        and_(
            Notificacao.read_at.is_not(None),
            Notificacao.read_at < cutoff_date,
        ),
        and_(
            Notificacao.resolved_at.is_not(None),
            Notificacao.resolved_at < cutoff_date,
        ),
    )


async def count(session: AsyncSession, days_threshold: int = 90) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Notificacao)
        .where(_condicao(_cutoff(days_threshold)))
    )
    return result.scalar() or 0


async def run(
    session: AsyncSession,
    days_threshold: int = 90,
) -> CleanupTaskResult:
    """Remove notificações lidas/resolvidas há mais de `days_threshold`."""
    start = time.monotonic()
    cutoff_date = _cutoff(days_threshold)

    try:
        delete_result = await session.execute(
            delete(Notificacao).where(_condicao(cutoff_date))
        )

        if delete_result.rowcount == 0:
            return CleanupTaskResult(
                task_name=TASK_NAME,
                status='skipped',
                duration_seconds=time.monotonic() - start,
                details={'reason': 'Nenhuma notificação encerrada antiga'},
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
