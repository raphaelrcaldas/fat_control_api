"""Agrupa evidências de passagem por localidade, respeitando os filtros."""

from collections.abc import Sequence

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.models.estatistica.etapa import Etapa, Missao
from fcontrol_api.models.shared.estados_cidades import (
    Cidade,
    GrupoLocEsp,
    LocEspIcao,
)
from fcontrol_api.schemas.cegep.gle_pesquisa import (
    EtapaContato,
    LocalidadeTocada,
    MissaoComLocEsp,
    PesquisaLocEspOut,
)

type LinhaPesquisa = Row[
    tuple[Etapa, Missao, LocEspIcao | None, LocEspIcao | None]
]


async def montar_pesquisa(
    session: AsyncSession,
    linhas: Sequence[LinhaPesquisa],
    grupo: int | None,
    loc_esp_id: int | None,
) -> PesquisaLocEspOut:
    """Recebe somente etapas já filtradas pela organização no router."""
    if not linhas:
        return PesquisaLocEspOut(total_missoes=0, missoes=[])

    # Carrega as localidades tocadas de uma vez: a etapa dá o id, e a tela
    # precisa de cidade/UF/grupo para nomear a passagem.
    ids_tocados = {
        loc.loc_esp_id
        for _, _, origem, destino in linhas
        for loc in (origem, destino)
        if loc is not None
    }
    locs_rows = (
        await session.execute(
            select(GrupoLocEsp, Cidade)
            .join(Cidade, Cidade.codigo == GrupoLocEsp.cidade_id)
            .options(selectinload(GrupoLocEsp.icaos))
            .where(GrupoLocEsp.id.in_(ids_tocados))
        )
    ).all()
    por_id = {
        loc.id: LocalidadeTocada(
            loc_esp_id=loc.id,
            cidade=cidade.nome,
            uf=cidade.uf,
            grupo=loc.grupo,
            icaos=sorted(item.icao for item in loc.icaos),
        )
        for loc, cidade in locs_rows
    }

    # Filtros que dependem da localidade tocada, não da etapa: aplicados
    # aqui porque uma etapa pode tocar duas (decolar de uma e pousar em
    # outra) e basta uma casar para a etapa entrar.
    #
    # Devolve as que casam, não um booleano: uma etapa SBEG (grupo A) ->
    # SBJU (grupo B) entra numa pesquisa por grupo A, mas só Manaus é
    # resposta à pergunta feita. Acumular as duas faria o cartão exibir um
    # badge B sob filtro A — respondendo outra pergunta.
    agrupadas: dict[int, dict] = {}
    for etapa, missao, origem, destino in linhas:
        tocados = {
            loc.loc_esp_id for loc in (origem, destino) if loc is not None
        }
        casam = {
            i
            for i in tocados
            if (grupo is None or por_id[i].grupo == grupo)
            and (loc_esp_id is None or i == loc_esp_id)
        }
        if not casam:
            continue

        grupo_missao = agrupadas.setdefault(
            missao.id,
            {
                'titulo': missao.titulo,
                'loc_ids': set(),
                'etapas': [],
            },
        )
        grupo_missao['loc_ids'].update(casam)
        grupo_missao['etapas'].append(
            EtapaContato(
                etapa_id=etapa.id,
                data=etapa.data,
                origem=etapa.origem,
                destino=etapa.destino,
                anv=etapa.anv,
                # Só os ICAOs que casam o filtro: é este campo que o
                # cartão usa para destacar a ponta especial, e destacar
                # uma ponta B sob filtro A contradiria os badges acima.
                icaos_loc_esp=sorted(
                    loc.icao
                    for loc in (origem, destino)
                    if loc is not None and loc.loc_esp_id in casam
                ),
            )
        )

    missoes = [
        MissaoComLocEsp(
            missao_id=mid,
            titulo=dados['titulo'],
            primeira_data=min(e.data for e in dados['etapas']),
            ultima_data=max(e.data for e in dados['etapas']),
            total_etapas=len(dados['etapas']),
            localidades=sorted(
                (por_id[i] for i in dados['loc_ids']),
                key=lambda loc: (loc.uf, loc.cidade),
            ),
            etapas=dados['etapas'],
        )
        for mid, dados in agrupadas.items()
    ]
    # Mais recente primeiro: é a missão que ainda está na cabeça de quem
    # consulta.
    missoes.sort(key=lambda m: (m.ultima_data, m.missao_id), reverse=True)

    return PesquisaLocEspOut(total_missoes=len(missoes), missoes=missoes)
