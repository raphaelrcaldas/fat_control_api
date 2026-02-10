"""
Script para limpar logs de login antigos (hard delete).

Remove permanentemente todos os logs de login com timestamp
anterior a 30 dias da data atual.

Uso:
    cd /path/to/api
    python -m scripts.cleanup_old_login_logs
"""

import asyncio
from datetime import datetime, timezone

from fcontrol_api.cleanup.tasks.old_login_logs import run
from fcontrol_api.database import get_session


async def main(days_threshold: int = 30):
    now = datetime.now(timezone.utc)
    print(f'[{now.isoformat()}] Iniciando limpeza de logs de login...')

    async for session in get_session():
        result = await run(session, days_threshold=days_threshold)

        print(f'Status: {result.status}')
        print(f'Registros afetados: {result.rows_affected}')
        print(f'Duracao: {result.duration_seconds:.2f}s')

        if result.status == 'success':
            print(f'Data de corte: {result.details["cutoff_date"]}')
        elif result.status == 'skipped':
            print(f'Motivo: {result.details["reason"]}')
        elif result.status == 'error':
            print(f'Erros: {result.errors}')

        end = datetime.now(timezone.utc)
        print(f'[{end.isoformat()}] Limpeza concluida!')
        break


if __name__ == '__main__':
    asyncio.run(main())
