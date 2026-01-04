"""
Script para limpar logs de login antigos (hard delete).

Remove permanentemente todos os logs de login com timestamp
anterior a 30 dias da data atual.

Uso:
    cd /path/to/api
    python -m scripts.cleanup_old_login_logs
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from fcontrol_api.database import get_session
from fcontrol_api.models.security.logs import UserActionLog


async def cleanup_old_login_logs(days_threshold: int = 30):
    """
    Remove permanentemente logs de login antigos do banco de dados.

    Args:
        days_threshold: Número de dias para considerar um log de login
                       como antigo. Default: 30 dias.
    """
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    now = datetime.now()

    print(f'[{now.isoformat()}] Iniciando limpeza de logs de login...')
    print(f'Data de corte: {cutoff_date.isoformat()} (registros anteriores)')

    async for session in get_session():
        # Contar logs de login antigos
        count_query = select(func.count(UserActionLog.id)).where(
            UserActionLog.action == 'login',
            UserActionLog.resource == 'auth',
            UserActionLog.timestamp < cutoff_date,
        )
        result = await session.execute(count_query)
        total = result.scalar()

        print(f'Encontrados {total} logs de login para remover.')

        if total == 0:
            print('Nenhum log de login antigo para limpar.')
            break

        # Hard delete dos logs de login antigos
        delete_result = await session.execute(
            delete(UserActionLog).where(
                UserActionLog.action == 'login',
                UserActionLog.resource == 'auth',
                UserActionLog.timestamp < cutoff_date,
            )
        )

        await session.commit()

        print(f'Logs de login deletados: {delete_result.rowcount}')
        print(f'[{datetime.now().isoformat()}] Limpeza concluida!')
        break


if __name__ == '__main__':
    asyncio.run(cleanup_old_login_logs())
