"""
Script para limpar indisponibilidades antigas (hard delete).

Remove permanentemente todas as indisponibilidades com date_end
anterior a 60 dias da data atual.

Uso:
    cd /path/to/api
    python -m scripts.cleanup_old_indisp
"""

import asyncio
from datetime import datetime, timezone

from fcontrol_api.cleanup.tasks.old_unavailability import (
    run as cleanup_old_unavailability,
)
from fcontrol_api.database import get_session


async def main(days_threshold: int = 60):
    now = datetime.now(timezone.utc)
    print(f'[{now.isoformat()}] Iniciando limpeza de indisponibilidades...')

    async for session in get_session():
        result = await cleanup_old_unavailability(
            session, days_threshold=days_threshold
        )

        print(f'Status: {result.status}')
        print(f'Registros afetados: {result.rows_affected}')
        print(f'Duracao: {result.duration_seconds:.2f}s')

        if result.status == 'success':
            print(f'Logs deletados: {result.details["logs_deleted"]}')
            print(f'IDs removidos: {result.details["ids_removed"]}')
        elif result.status == 'skipped':
            print(f'Motivo: {result.details["reason"]}')
        elif result.status == 'error':
            print(f'Erros: {result.errors}')

        end = datetime.now(timezone.utc)
        print(f'[{end.isoformat()}] Limpeza concluida!')
        break


if __name__ == '__main__':
    asyncio.run(main())
