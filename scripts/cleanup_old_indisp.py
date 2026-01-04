"""
Script para limpar indisponibilidades antigas (hard delete).

Remove permanentemente todas as indisponibilidades com date_end
anterior a 60 dias da data atual.

Uso:
    cd /path/to/api
    python -m scripts.cleanup_old_indisp
"""

import asyncio
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.security.logs import UserActionLog


async def cleanup_old_indisps(days_threshold: int = 60):
    """
    Remove permanentemente indisponibilidades antigas do banco de dados.

    Args:
        days_threshold: Número de dias para considerar uma indisponibilidade
                       como antiga. Default: 60 dias.
    """
    cutoff_date = date.today() - timedelta(days=days_threshold)
    now = datetime.now(timezone.utc)

    print(f'[{now.isoformat()}] Iniciando limpeza de indisponibilidades...')
    print(f'Data de corte: {cutoff_date} (registros com date_end anterior)')

    async for session in get_session():
        # Buscar IDs das indisponibilidades antigas para log
        query = select(Indisp.id).where(Indisp.date_end < cutoff_date)
        result = await session.execute(query)
        ids_to_delete = [id for (id,) in result.all()]

        total = len(ids_to_delete)
        print(f'Encontradas {total} indisponibilidades para remover.')

        if total == 0:
            print('Nenhuma indisponibilidade antiga para limpar.')
            break

        # Excluir logs relacionados para evitar registros órfãos
        logs_delete_result = await session.execute(
            delete(UserActionLog).where(
                UserActionLog.resource == 'indisp',
                UserActionLog.resource_id.in_(ids_to_delete),
            )
        )
        logs_deleted = logs_delete_result.rowcount

        # Hard delete das indisponibilidades
        await session.execute(
            delete(Indisp).where(Indisp.id.in_(ids_to_delete))
        )

        await session.commit()

        print(f'Logs deletados: {logs_deleted}')
        print(f'Indisponibilidades deletadas: {total}')
        print(f'IDs removidos: {ids_to_delete}')
        print(f'[{datetime.now(timezone.utc).isoformat()}] Limpeza concluida!')
        break


if __name__ == '__main__':
    asyncio.run(cleanup_old_indisps())
