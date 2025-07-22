from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.public.posto_grad import Soldo


async def cache_diarias(session: AsyncSession):
    result = await session.scalars(select(DiariaValor))
    valores = result.all()

    cache = defaultdict(list)

    for v in valores:
        chave = (v.grupo_pg, v.grupo_cid)
        cache[chave].append(v)

    return cache


async def cache_soldos(session: AsyncSession):
    result = await session.scalars(select(Soldo))
    soldos = result.all()

    cache = defaultdict(list)

    for s in soldos:
        cache[s.pg].append(s)

    return cache
