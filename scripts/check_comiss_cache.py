"""
Diagnóstico READ-ONLY do cache dos comissionamentos.

Para cada comissionamento, recomputa o agregado AO VIVO a partir das
missões (mesma lógica de `recalcular_cache_comiss`, porém sem escrever) e
compara com o `cache_calc` persistido. Lista os comissionamentos cujo
cache está inconsistente — sem alterar nada no banco.

Uso:
    cd /path/to/api
    uv run python scripts/check_comiss_cache.py
"""

import asyncio

from sqlalchemy import and_, select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.schemas.cegep.missoes import FragMisSchema
from fcontrol_api.services.comis import filtro_missoes_periodo
from fcontrol_api.services.custos import custo_missao

# Tolerância para agregados monetários/diárias (ponto flutuante).
TOL = 0.01


async def _agregado_ao_vivo(comiss: Comissionamento, session) -> dict:
    """Recomputa os agregados a partir das missões, sem persistir."""
    query = (
        select(FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == comiss.user_id,
                UserFrag.sit == 'c',
                UserFrag.frag_id == FragMis.id,
            ),
        )
        .where(
            filtro_missoes_periodo(comiss.uae, comiss.data_ab, comiss.data_fc)
        )
        .order_by(FragMis.afast)
    )

    registros = (await session.execute(query)).all()

    dias = 0
    diarias = 0.0
    vals = 0.0
    inconsistentes = 0

    for missao, user_frag in registros:
        mis = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )
        mis = custo_missao(user_frag.p_g, user_frag.sit, mis)
        if mis.get('custo_inconsistente'):
            inconsistentes += 1
        dias += mis['dias']
        diarias += mis['diarias']
        vals += mis['valor_total']

    return {
        'dias_comp': dias,
        'diarias_comp': diarias,
        'vals_comp': round(vals, 2),
        'missoes_count': len(registros),
        'missoes_inconsistentes': inconsistentes,
    }


def _motivos(cache: dict, vivo: dict) -> list[str]:
    motivos: list[str] = []

    if not cache:
        motivos.append('cache_calc vazio/inexistente')

    if vivo['missoes_inconsistentes'] > 0:
        motivos.append(
            f'{vivo["missoes_inconsistentes"]} missão(ões) com '
            'custo individual desatualizado'
        )

    if cache.get('missoes_count', 0) != vivo['missoes_count']:
        motivos.append(
            f'missoes_count: cache={cache.get("missoes_count", 0)} '
            f'vivo={vivo["missoes_count"]}'
        )

    if vivo['dias_comp'] != cache.get('dias_comp', 0):
        motivos.append(
            f'dias_comp: cache={cache.get("dias_comp", 0)} '
            f'vivo={vivo["dias_comp"]}'
        )

    if abs(vivo['diarias_comp'] - cache.get('diarias_comp', 0)) > TOL:
        motivos.append(
            f'diarias_comp: cache={cache.get("diarias_comp", 0)} '
            f'vivo={vivo["diarias_comp"]}'
        )

    if abs(vivo['vals_comp'] - cache.get('vals_comp', 0)) > TOL:
        motivos.append(
            f'vals_comp: cache={cache.get("vals_comp", 0)} '
            f'vivo={vivo["vals_comp"]}'
        )

    return motivos


async def check_all_cache():
    """Compara cache persistido vs agregado ao vivo (sem escrever)."""
    async for session in get_session():
        comiss_list = (
            await session.scalars(
                select(Comissionamento).order_by(Comissionamento.id)
            )
        ).all()

        print(f'Verificando {len(comiss_list)} comissionamentos...\n')

        inconsistentes: list[tuple[int, str, list[str]]] = []

        for comiss in comiss_list:
            cache = comiss.cache_calc or {}
            vivo = await _agregado_ao_vivo(comiss, session)
            motivos = _motivos(cache, vivo)
            if motivos:
                inconsistentes.append((comiss.id, comiss.uae, motivos))

        if not inconsistentes:
            print('✅ Nenhum cache inconsistente encontrado.')
        else:
            print(
                f'⚠️  {len(inconsistentes)} de {len(comiss_list)} '
                'comissionamentos com cache inconsistente:\n'
            )
            for comiss_id, uae, motivos in inconsistentes:
                print(f'  Comiss #{comiss_id} [{uae}]')
                for m in motivos:
                    print(f'      - {m}')

        # READ-ONLY: rollback explícito, nada é persistido.
        await session.rollback()
        break


if __name__ == '__main__':
    asyncio.run(check_all_cache())
