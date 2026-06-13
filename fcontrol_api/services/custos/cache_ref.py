"""Caches de referência usados no cálculo de custos.

Carregam de uma vez as tabelas de domínio (diárias, soldos, grupos de pg
e de cidade) para evitar N+1 durante a materialização do cache de uma
missão. São dados que mudam pouco e impactam todo o sistema — futura
detecção de drift por alteração nessas tabelas (fase 2) parte daqui.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.cegep.diarias import (
    DiariaValor,
    GrupoCidade,
    GrupoPg,
)
from fcontrol_api.models.shared.posto_grad import Soldo


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


async def carregar_caches_custo(session: AsyncSession) -> tuple:
    """Carrega de uma vez os caches de referência usados no cálculo de
    custos (diárias, soldos, grupos de pg e de cidade)."""
    valores_cache = await cache_diarias(session)
    soldos_cache = await cache_soldos(session)
    grupos_pg = dict(
        (await session.execute(select(GrupoPg.pg_short, GrupoPg.grupo))).all()
    )
    grupos_cidade = dict(
        (
            await session.execute(
                select(GrupoCidade.cidade_id, GrupoCidade.grupo)
            )
        ).all()
    )
    return valores_cache, soldos_cache, grupos_pg, grupos_cidade
