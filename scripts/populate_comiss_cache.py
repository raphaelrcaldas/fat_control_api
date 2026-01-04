"""
Script para popular o cache JSONB de todos os comissionamentos existentes.

Uso:
    cd /path/to/api
    python -m fcontrol_api.scripts.populate_comiss_cache
"""

import asyncio

from sqlalchemy import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.services.comis import recalcular_cache_comiss


async def populate_all_cache():
    """Recalcula o cache de todos os comissionamentos."""
    async for session in get_session():
        # Buscar todos os comissionamentos
        result = await session.execute(select(Comissionamento.id))
        comiss_ids = [id for (id,) in result.all()]

        print(
            f'Encontrados {len(comiss_ids)} comissionamentos para recalcular'
        )

        for i, comiss_id in enumerate(comiss_ids, 1):
            try:
                cache = await recalcular_cache_comiss(comiss_id, session)
                print(
                    f'[{i}/{len(comiss_ids)}] Comiss #{comiss_id}: '
                    f'dias={cache.get("dias_comp", 0)}, '
                    f'vals={cache.get("vals_comp", 0)}, '
                    f'completude={cache.get("completude", 0)}'
                )
            except Exception as e:
                print(
                    f'[{i}/{len(comiss_ids)}] Comiss #{comiss_id}: ERRO - {e}'
                )

        await session.commit()
        print('\n✅ Cache populado com sucesso!')
        break


if __name__ == '__main__':
    asyncio.run(populate_all_cache())
