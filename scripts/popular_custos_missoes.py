"""
Script para popular a coluna custos JSONB em todas as missões existentes.

Execução:
    poetry run python scripts/popular_custos_missoes.py
"""

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from tqdm import tqdm

from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import FragMis
from fcontrol_api.schemas.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.services.financeiro import cache_diarias, cache_soldos
from fcontrol_api.settings import Settings
from fcontrol_api.utils.financeiro import calcular_custos_frag_mis


async def popular_custos():
    """Popula custos de todas as missões existentes no banco."""

    print('=' * 80)
    print('SCRIPT DE POPULAÇÃO DE CUSTOS - FragMis')
    print('=' * 80)
    print()

    # Configurar engine e session
    settings = Settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # 1. Carregar caches uma única vez (reutilizar para todas as missões)
        print('📦 Carregando caches...')
        valores_cache = await cache_diarias(session)
        soldos_cache = await cache_soldos(session)

        grupos_pg = dict(
            (
                await session.execute(select(GrupoPg.pg_short, GrupoPg.grupo))
            ).all()
        )
        grupos_cidade = dict(
            (
                await session.execute(
                    select(GrupoCidade.cidade_id, GrupoCidade.grupo)
                )
            ).all()
        )
        print(f'   ✓ {len(valores_cache)} valores de diária carregados')
        print(f'   ✓ {len(soldos_cache)} valores de soldo carregados')
        print(f'   ✓ {len(grupos_pg)} grupos de PG carregados')
        print(f'   ✓ {len(grupos_cidade)} grupos de cidade carregados')
        print()

        # 2. Buscar todas as missões com eager loading
        print('🔍 Buscando missões no banco...')
        stmt = (
            select(FragMis)
            .options(
                selectinload(FragMis.pernoites),
                selectinload(FragMis.users),
            )
            .order_by(FragMis.id)
        )

        result = await session.execute(stmt)
        missoes = result.scalars().all()

        total_missoes = len(missoes)
        print(f'   ✓ {total_missoes} missões encontradas')
        print()

        if total_missoes == 0:
            print('⚠️  Nenhuma missão encontrada no banco.')
            return

        # 3. Processar cada missão com barra de progresso
        print('⚙️  Calculando custos...')
        print()

        sucesso = 0
        erros = 0
        erros_detalhes = []

        # Barra de progresso com tqdm
        with tqdm(
            total=total_missoes,
            desc='Processando missões',
            unit='missão',
            ncols=100,
        ) as pbar:
            for missao in missoes:
                try:
                    # Mostrar qual missão está sendo processada
                    info_missao = (
                        f'ID {missao.id:4d} | '
                        f'{missao.tipo_doc}-{missao.n_doc:03d} | '
                        f'{missao.desc[:40]:40s}'
                    )
                    pbar.set_description(f'🔄 {info_missao}')

                    # Preparar inputs validados
                    pernoites_input = [
                        CustoPernoiteInput(
                            id=pnt.id,
                            data_ini=pnt.data_ini,
                            data_fim=pnt.data_fim,
                            meia_diaria=pnt.meia_diaria,
                            acrec_desloc=pnt.acrec_desloc,
                            cidade_codigo=pnt.cidade_id,
                        )
                        for pnt in missao.pernoites
                    ]

                    users_frag_input = [
                        CustoUserFragInput(
                            p_g=uf.p_g,
                            sit=uf.sit,
                        )
                        for uf in missao.users
                    ]

                    frag_mis_input = CustoFragMisInput(
                        acrec_desloc=missao.acrec_desloc
                    )

                    # Calcular custos
                    custos = calcular_custos_frag_mis(
                        frag_mis_input,
                        users_frag_input,
                        pernoites_input,
                        grupos_pg,
                        grupos_cidade,
                        valores_cache,
                        soldos_cache,
                    )

                    # Atualizar missão
                    missao.custos = custos
                    sucesso += 1

                except Exception as e:
                    erros += 1
                    erros_detalhes.append({
                        'id': missao.id,
                        'desc': missao.desc,
                        'erro': str(e),
                    })
                    pbar.set_description(f'❌ Erro na missão {missao.id}')

                finally:
                    pbar.update(1)

        # 4. Commit final
        print()
        print('💾 Salvando alterações no banco...')
        await session.commit()
        print('   ✓ Alterações salvas com sucesso!')

        # 5. Relatório final
        print()
        print('=' * 80)
        print('RELATÓRIO FINAL')
        print('=' * 80)
        print(f'Total de missões processadas: {total_missoes}')
        print(f'✅ Sucesso: {sucesso}')
        print(f'❌ Erros: {erros}')
        print()

        if erros > 0:
            print('DETALHES DOS ERROS:')
            print('-' * 80)
            for erro in erros_detalhes:
                id_erro = f'{erro["id"]:4d}'
                desc = f'{erro["desc"][:40]:40s}'
                print(f'ID {id_erro} | {desc} | {erro["erro"]}')
            print()

        # Taxa de sucesso
        taxa_sucesso = (
            (sucesso / total_missoes * 100) if total_missoes > 0 else 0
        )
        print(f'Taxa de sucesso: {taxa_sucesso:.1f}%')
        print('=' * 80)

    await engine.dispose()


if __name__ == '__main__':
    print()
    inicio = datetime.now()
    asyncio.run(popular_custos())
    fim = datetime.now()
    duracao = (fim - inicio).total_seconds()
    print()
    print(f'⏱️  Tempo total de execução: {duracao:.2f} segundos')
    print()
