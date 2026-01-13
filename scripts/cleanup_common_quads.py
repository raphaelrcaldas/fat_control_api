"""
Script para limpar quadrinhos comuns (hard delete).

Dois modos de uso:

1. LIMPEZA TOTAL (sem parametros de filtro):
   Itera sobre todas as combinacoes de tipo_quad, uae, funcao, proj.

2. LIMPEZA INDIVIDUAL (com parametros de filtro):
   Limpa apenas uma combinacao especifica.

Para cada combinacao, identifica o min_length (menor quantidade de quadrinhos
entre todos os tripulantes do grupo) e deleta (min_length - manter) quadrinhos.

Uso:
    cd /path/to/api

    # Limpeza total - manter 5 quadrinhos (default), dry run
    python -m scripts.cleanup_common_quads --dry-run

    # Limpeza total - manter 3 quadrinhos
    python -m scripts.cleanup_common_quads --manter 3

    # Limpeza individual - manter 3 quadrinhos
    python -m scripts.cleanup_common_quads \\
        --tipo-quad 1 --funcao mc --uae 11gt --proj kc-390 --manter 3

Exemplo:
    Se min_length=16 e --manter=5 (default), deleta os primeiros 11 (16-5).
    Se min_length=16 e --manter=3, deleta os primeiros 13 (16-3).
"""

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.quads import Quad, QuadsGroup, QuadsType
from fcontrol_api.models.public.tripulantes import Tripulante


async def get_all_combinations(session):
    """
    Obtem todas as combinacoes unicas de (tipo_quad, uae, func, proj).
    """
    # Buscar todos os QuadsType com seus grupos (via join) e funcs
    quads_types_result = await session.execute(
        select(QuadsType, QuadsGroup.uae)
        .join(QuadsGroup, QuadsType.group_id == QuadsGroup.id)
        .options(selectinload(QuadsType.funcs))
    )
    quads_types_data = quads_types_result.all()

    # Buscar projetos unicos dos tripulantes ativos
    projs_result = await session.execute(
        select(distinct(Funcao.proj))
        .join(Tripulante)
        .where(
            Tripulante.active,
            Funcao.oper != 'al',
            Funcao.data_op.is_not(None),
        )
    )
    projs = [proj for (proj,) in projs_result.all()]

    combinations = []
    for quad_type, uae in quads_types_data:
        funcs_list = [qf.func for qf in quad_type.funcs]

        for funcao in funcs_list:
            for proj in projs:
                combinations.append({
                    'tipo_quad': quad_type.id,
                    'tipo_quad_name': quad_type.short,
                    'uae': uae,
                    'funcao': funcao,
                    'proj': proj,
                })

    return combinations


async def cleanup_for_combination(
    session,
    tipo_quad: int,
    funcao: str,
    uae: str,
    proj: str,
    dry_run: bool,
    manter: int = 5,
):
    """
    Executa a limpeza para uma combinacao especifica.
    Retorna dict com total e detalhamento por tripulante.

    Args:
        manter: Quantidade de quadrinhos a manter.
                Deleta (min_length - manter) quadrinhos.
    """
    # 1. CTE para obter os IDs dos tripulantes que correspondem aos filtros
    trip_ids_cte = (
        select(Tripulante.id)
        .join(Funcao)
        .where(
            Tripulante.uae == uae,
            Tripulante.active,
            Funcao.func == funcao,
            Funcao.oper != 'al',
            Funcao.proj == proj,
            Funcao.data_op.is_not(None),
        )
        .cte('trip_ids_cte')
    )

    # 2. CTE para contar o total de quadrinhos de cada tripulante
    quad_counts_cte = (
        select(Quad.trip_id, func.count(Quad.id).label('total_quads'))
        .where(
            Quad.trip_id.in_(select(trip_ids_cte.c.id)),
            Quad.type_id == tipo_quad,
        )
        .group_by(Quad.trip_id)
        .cte('quad_counts_cte')
    )

    # 3. Buscar tripulantes e contagem (incluindo trig para identificacao)
    trip_query = (
        select(Tripulante.id, Tripulante.trig, quad_counts_cte.c.total_quads)
        .outerjoin(quad_counts_cte, Tripulante.id == quad_counts_cte.c.trip_id)
        .where(Tripulante.id.in_(select(trip_ids_cte.c.id)))
    )

    trips_result = await session.execute(trip_query)
    trip_data = trips_result.all()

    if not trip_data:
        return {'total': 0, 'by_trip': {}}

    # Extrai os IDs, trigs e o min_length dos resultados
    trip_ids = [trip_id for trip_id, _, _ in trip_data]
    trip_trigs = {trip_id: trig for trip_id, trig, _ in trip_data}
    counts = [
        (total_quads if total_quads is not None else 0)
        for _, _, total_quads in trip_data
    ]
    min_length = min(counts)

    if min_length == 0:
        return {'total': 0, 'by_trip': {}}

    # 4. CTE para rankear os quadrinhos
    # n_slice = quantos deletar = min_length - manter
    n_slice = min_length - manter

    if n_slice <= 0:
        return {'total': 0, 'by_trip': {}}

    ranked_quads_cte = (
        select(
            Quad.id.label('quad_id'),
            Quad.trip_id,
            Quad.value,
            func
            .row_number()
            .over(
                partition_by=Quad.trip_id,
                order_by=Quad.value.asc().nullsfirst(),
            )
            .label('rn'),
        )
        .where(Quad.trip_id.in_(trip_ids), Quad.type_id == tipo_quad)
        .cte('ranked_quads')
    )

    # 5. Query para buscar os quadrinhos COMUNS (rn <= n_slice)
    common_quads_query = select(
        ranked_quads_cte.c.quad_id,
        ranked_quads_cte.c.trip_id,
    ).where(ranked_quads_cte.c.rn <= n_slice)

    common_quads_result = await session.execute(common_quads_query)
    common_quads = common_quads_result.all()

    if not common_quads:
        return {'total': 0, 'by_trip': {}}

    # Agrupa por tripulante
    by_trip = defaultdict(int)
    ids_to_delete = []
    for quad_id, trip_id in common_quads:
        ids_to_delete.append(quad_id)
        by_trip[trip_trigs.get(trip_id, f'ID:{trip_id}')] += 1

    total = len(ids_to_delete)

    if not dry_run:
        await session.execute(delete(Quad).where(Quad.id.in_(ids_to_delete)))

    return {'total': total, 'by_trip': dict(by_trip)}


async def cleanup_single(
    tipo_quad: int,
    funcao: str,
    uae: str,
    proj: str,
    dry_run: bool = False,
    manter: int = 5,
):
    """
    Remove quadrinhos comuns de uma combinacao especifica.
    """
    now = datetime.now(timezone.utc)

    print(f'[{now.isoformat()}] Iniciando limpeza individual...')
    print(
        f'Parametros: tipo_quad={tipo_quad}, funcao={funcao}, '
        f'uae={uae}, proj={proj}, manter={manter}'
    )
    if dry_run:
        print('*** MODO DRY RUN - Nenhum dado sera deletado ***\n')

    async for session in get_session():
        result = await cleanup_for_combination(
            session,
            tipo_quad=tipo_quad,
            funcao=funcao,
            uae=uae,
            proj=proj,
            dry_run=dry_run,
            manter=manter,
        )

        deleted = result['total']
        action = 'Seriam deletados' if dry_run else 'Deletados'

        if deleted > 0:
            print(f'{action}: {deleted} quadrinhos')
            print('Detalhamento por tripulante:')
            for trig, count in result['by_trip'].items():
                print(f'  {trig}: {count}')

            if not dry_run:
                await session.commit()
        else:
            print('Nenhum quadrinho comum encontrado.')

        break

    print(f'[{datetime.now(timezone.utc).isoformat()}] Limpeza concluida!')


async def cleanup_all(dry_run: bool = False, manter: int = 5):
    """
    Remove permanentemente quadrinhos comuns de todo o sistema.

    Args:
        dry_run: Se True, apenas mostra o que seria deletado sem executar
        manter: Quantidade de quadrinhos a manter por tripulante
    """
    now = datetime.now(timezone.utc)

    print(f'[{now.isoformat()}] Iniciando limpeza total...')
    print(f'Mantendo {manter} quadrinho(s) por tripulante')
    if dry_run:
        print('*** MODO DRY RUN - Nenhum dado sera deletado ***\n')

    total_deleted = 0
    combinations_processed = 0
    combinations_with_deletions = 0

    async for session in get_session():
        # Obter todas as combinacoes
        combinations = await get_all_combinations(session)
        print(f'Total de combinacoes a processar: {len(combinations)}\n')

        # Agrupar por tipo de quadrinho para melhor visualizacao
        by_type = defaultdict(list)
        for combo in combinations:
            by_type[combo['tipo_quad_name']].append(combo)

        for tipo_name, combos in by_type.items():
            print(f'=== Tipo: {tipo_name} ===')
            type_deleted = 0

            for combo in combos:
                result = await cleanup_for_combination(
                    session,
                    tipo_quad=combo['tipo_quad'],
                    funcao=combo['funcao'],
                    uae=combo['uae'],
                    proj=combo['proj'],
                    dry_run=dry_run,
                    manter=manter,
                )

                combinations_processed += 1
                deleted = result['total']

                if deleted > 0:
                    combinations_with_deletions += 1
                    type_deleted += deleted
                    action = 'Seriam deletados' if dry_run else 'Deletados'
                    combo_key = (
                        f'{combo["uae"]}|{combo["funcao"]}|{combo["proj"]}'
                    )
                    print(f'  [{combo_key}] {action}: {deleted} quadrinhos')
                    # Detalhamento por tripulante
                    for trig, count in result['by_trip'].items():
                        print(f'      {trig}: {count}')

            if type_deleted > 0:
                total_deleted += type_deleted
                print(f'  Subtotal {tipo_name}: {type_deleted}\n')
            else:
                print('  Nenhum quadrinho comum encontrado\n')

        if not dry_run:
            await session.commit()

        break

    print('=' * 50)
    print(f'Combinacoes processadas: {combinations_processed}')
    print(f'Combinacoes com delecoes: {combinations_with_deletions}')
    action = 'Seriam deletados' if dry_run else 'Total deletado'
    print(f'{action}: {total_deleted} quadrinhos')
    print(f'[{datetime.now(timezone.utc).isoformat()}] Limpeza concluida!')


def main():
    parser = argparse.ArgumentParser(
        description='Limpa quadrinhos comuns (total ou individual)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Apenas mostra o que seria deletado, sem executar',
    )
    parser.add_argument(
        '--manter',
        type=int,
        default=5,
        help='Quantidade de quadrinhos a manter (default: 5)',
    )
    parser.add_argument(
        '--tipo-quad',
        type=int,
        default=None,
        help='ID do tipo de quadrinho (para limpeza individual)',
    )
    parser.add_argument(
        '--funcao',
        type=str,
        default=None,
        help='Funcao dos tripulantes (para limpeza individual)',
    )
    parser.add_argument(
        '--uae',
        type=str,
        default=None,
        help='UAE dos tripulantes (para limpeza individual)',
    )
    parser.add_argument(
        '--proj',
        type=str,
        default=None,
        help='Projeto dos tripulantes (para limpeza individual)',
    )

    args = parser.parse_args()

    # Se todos os parametros individuais foram passados, limpeza individual
    individual_params = [args.tipo_quad, args.funcao, args.uae, args.proj]

    if all(p is not None for p in individual_params):
        asyncio.run(
            cleanup_single(
                tipo_quad=args.tipo_quad,
                funcao=args.funcao,
                uae=args.uae,
                proj=args.proj,
                dry_run=args.dry_run,
                manter=args.manter,
            )
        )
    elif any(p is not None for p in individual_params):
        print('Erro: Para limpeza individual, informe todos os parametros:')
        print('  --tipo-quad, --funcao, --uae, --proj')
        print('\nOu nao passe nenhum para limpeza total.')
    else:
        asyncio.run(cleanup_all(dry_run=args.dry_run, manter=args.manter))


if __name__ == '__main__':
    main()
