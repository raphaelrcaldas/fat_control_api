"""Router das localidades especiais (GLE).

**Tabela global, sem escopo de organizacao.** A classificacao GLE e
nacional e `grupos_loc_esp` nao tem coluna de org: filtrar por
`ActiveOrg` seria inventar um escopo que o dado nao tem. O gate de RBAC
continua valendo — o que e global e o dado, nao o acesso.

Contexto de dominio em `docs/dominio/gle.md`.
"""

from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import Etapa, Missao, OIEtapa
from fcontrol_api.models.shared.estados_cidades import (
    Cidade,
    GrupoLocEsp,
    LocEspIcao,
)
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.gle import (
    LocEspCreate,
    LocEspOut,
    LocEspUpdate,
)
from fcontrol_api.schemas.cegep.gle_pesquisa import (
    EtapaContato,
    LocalidadeTocada,
    MissaoComLocEsp,
    PesquisaLocEspOut,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

LocEspId = Annotated[int, Path()]

router = APIRouter(prefix='/gle', tags=['CEGEP'])

RESOURCE_GLE = 'loc_esp'

ViewGle = Depends(permission_checker('cegep.gle', 'view'))
CreateGle = Depends(permission_checker('cegep.gle', 'create'))
UpdateGle = Depends(permission_checker('cegep.gle', 'update'))
DeleteGle = Depends(permission_checker('cegep.gle', 'delete'))

# A pesquisa le etapa, nao a tabela de referencia: o gate e o da etapa, e o
# escopo e a org ativa (etapa pertence a missao, que pertence a uma org).
ViewEtapa = Depends(permission_checker('estatistica.etapas', 'view'))


def _to_out(loc: GrupoLocEsp) -> LocEspOut:
    return LocEspOut(
        id=loc.id,
        cidade_id=loc.cidade_id,
        grupo=loc.grupo,
        fuso=loc.fuso,
        cidade=loc.cidade,
        icaos=sorted(item.icao for item in loc.icaos),
    )


def _snapshot(loc: GrupoLocEsp) -> dict:
    return {
        'cidade_id': loc.cidade_id,
        'grupo': loc.grupo,
        'fuso': loc.fuso,
        'icaos': sorted(item.icao for item in loc.icaos),
    }


async def _assert_cidade_existe(session: AsyncSession, cidade_id: int) -> None:
    existe = await session.scalar(
        select(Cidade.codigo).where(Cidade.codigo == cidade_id)
    )
    if not existe:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='Cidade não encontrada',
        )


async def _assert_cidade_livre(
    session: AsyncSession, cidade_id: int, excluir_id: int | None = None
) -> None:
    """Uma cidade e localidade especial uma unica vez (unique no banco).

    Checado aqui para devolver mensagem util em vez do IntegrityError.
    """
    stmt = select(GrupoLocEsp.id).where(GrupoLocEsp.cidade_id == cidade_id)
    if excluir_id is not None:
        stmt = stmt.where(GrupoLocEsp.id != excluir_id)
    if await session.scalar(stmt):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Esta cidade já está cadastrada como localidade especial',
        )


async def _assert_icaos_livres(
    session: AsyncSession, icaos: list[str], excluir_id: int | None = None
) -> None:
    """Um aerodromo atende uma so localidade (unique no banco).

    Sem esta checagem, mover um ICAO de uma localidade para outra devolve
    IntegrityError 500 em vez de dizer onde ele ja esta.
    """
    if not icaos:
        return
    stmt = (
        select(LocEspIcao.icao, Cidade.nome, Cidade.uf)
        .join(GrupoLocEsp, GrupoLocEsp.id == LocEspIcao.loc_esp_id)
        .join(Cidade, Cidade.codigo == GrupoLocEsp.cidade_id)
        .where(LocEspIcao.icao.in_(icaos))
    )
    if excluir_id is not None:
        stmt = stmt.where(LocEspIcao.loc_esp_id != excluir_id)
    conflitos = (await session.execute(stmt)).all()
    if conflitos:
        ocupados = ', '.join(
            f'{icao} (em {nome} - {uf})' for icao, nome, uf in conflitos
        )
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'ICAO já vinculado a outra localidade: {ocupados}',
        )


@router.get(
    '',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[LocEspOut]],
    dependencies=[ViewGle],
)
async def list_localidades(
    session: Session,
    grupo: Annotated[int | None, Query(ge=1, le=2)] = None,
    uf: Annotated[str | None, Query(max_length=2)] = None,
    search: Annotated[str | None, Query()] = None,
) -> ApiResponse[list[LocEspOut]]:
    """Lista as localidades especiais.

    Sem paginacao: sao poucas dezenas de municipios no pais inteiro, e a
    tela precisa do conjunto todo para filtrar no cliente.

    `search` casa nome da cidade (sem acento) ou ICAO.
    """
    stmt = (
        select(GrupoLocEsp)
        .join(Cidade, Cidade.codigo == GrupoLocEsp.cidade_id)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .order_by(Cidade.nome, GrupoLocEsp.id)
    )

    if grupo is not None:
        stmt = stmt.where(GrupoLocEsp.grupo == grupo)
    if uf:
        stmt = stmt.where(Cidade.uf == uf.upper())
    if search:
        termo = search.strip()
        # "Contém", como na cidade: o campo é um só ("Município ou
        # ICAO..."), e com prefixo digitar "BEG" não acharia SBEG — o
        # usuário concluiria que o ICAO não está cadastrado.
        por_icao = select(LocEspIcao.loc_esp_id).where(
            LocEspIcao.icao.ilike(f'%{termo}%')
        )
        stmt = stmt.where(
            sql_func.unaccent(Cidade.nome).ilike(
                sql_func.unaccent(f'%{termo}%')
            )
            | GrupoLocEsp.id.in_(por_icao)
        )

    localidades = (await session.scalars(stmt)).all()
    return success_response(data=[_to_out(loc) for loc in localidades])


@router.get(
    '/pesquisa',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[PesquisaLocEspOut],
    dependencies=[ViewEtapa],
)
async def pesquisar_missoes(
    session: Session,
    active_org: ActiveOrg,
    data_ini: Annotated[date | None, Query()] = None,
    data_fim: Annotated[date | None, Query()] = None,
    grupo: Annotated[int | None, Query(ge=1, le=2)] = None,
    loc_esp_id: Annotated[int | None, Query()] = None,
) -> ApiResponse[PesquisaLocEspOut]:
    """Missões que passaram por localidade especial.

    A pergunta é **binária**: a missão passou por lá ou não. Por isso o
    resultado agrupa por missão e as etapas descem só como evidência —
    não é relatório de horas nem de permanência.

    **Tocar em qualquer ponta conta**: origem e destino contam igual,
    porque ambos provam a passagem. Uma etapa que liga duas localidades
    especiais aparece uma vez, com os dois ICAOs em `icaos_loc_esp`.

    Só entram etapas com **esforço aéreo cadastrado** (ao menos uma
    `OIEtapa`): sem ele o lançamento está incompleto e não sustenta a
    passagem.

    Precisa vir declarada antes de `/{id}`, senão o path casa com a rota
    de detalhe e `pesquisa` reprova em 422.

    Sem paginação: a janela de datas é o que limita o volume, como em
    `estatistica/etapas`.
    """
    # `etapas` vive no schema `estatistica` e a ponte em `public` — o JOIN
    # cruza schemas, e o SQLAlchemy resolve pelos models.
    origem_loc = aliased(LocEspIcao, name='origem_loc')
    destino_loc = aliased(LocEspIcao, name='destino_loc')

    # Esforço aéreo vem por OIEtapa (`esf_aer_id` obrigatório lá): etapa sem
    # nenhuma OI é lançamento incompleto e não entra. EXISTS em vez de JOIN
    # porque a etapa pode ter várias OIs e o JOIN a duplicaria.
    tem_esf_aer = (
        select(OIEtapa.id).where(OIEtapa.etapa_id == Etapa.id).exists()
    )

    stmt = (
        select(Etapa, Missao, origem_loc, destino_loc)
        .join(Missao, Missao.id == Etapa.missao_id)
        .outerjoin(origem_loc, origem_loc.icao == Etapa.origem)
        .outerjoin(destino_loc, destino_loc.icao == Etapa.destino)
        .where(
            Missao.uae == active_org,
            # Simulador não sai do chão: não passa por localidade nenhuma.
            Missao.is_simulador.is_(False),
            (origem_loc.id.is_not(None)) | (destino_loc.id.is_not(None)),
            tem_esf_aer,
        )
        .order_by(Etapa.data, Etapa.dep, Etapa.id)
    )

    if data_ini:
        stmt = stmt.where(Etapa.data >= data_ini)
    if data_fim:
        stmt = stmt.where(Etapa.data <= data_fim)

    linhas = (await session.execute(stmt)).all()
    if not linhas:
        return success_response(
            data=PesquisaLocEspOut(total_missoes=0, missoes=[])
        )

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
    def locs_que_casam(ids: set[int]) -> set[int]:
        alvo = ids
        if grupo is not None:
            alvo = {i for i in alvo if por_id[i].grupo == grupo}
        if loc_esp_id is not None:
            alvo = {i for i in alvo if i == loc_esp_id}
        return alvo

    agrupadas: dict[int, dict] = {}
    for etapa, missao, origem, destino in linhas:
        tocados = {
            loc.loc_esp_id for loc in (origem, destino) if loc is not None
        }
        casam = locs_que_casam(tocados)
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

    return success_response(
        data=PesquisaLocEspOut(total_missoes=len(missoes), missoes=missoes)
    )


@router.get(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[LocEspOut],
    dependencies=[ViewGle],
)
async def get_localidade(
    id: LocEspId, session: Session
) -> ApiResponse[LocEspOut]:
    loc = await session.scalar(
        select(GrupoLocEsp)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .where(GrupoLocEsp.id == id)
    )
    if not loc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Localidade não encontrada',
        )
    return success_response(data=_to_out(loc))


@router.post(
    '',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[LocEspOut],
    dependencies=[CreateGle],
)
async def create_localidade(
    data: LocEspCreate, session: Session, current_user: CurrentUser
) -> ApiResponse[LocEspOut]:
    await _assert_cidade_existe(session, data.cidade_id)
    await _assert_cidade_livre(session, data.cidade_id)
    await _assert_icaos_livres(session, data.icaos)

    loc = GrupoLocEsp(
        cidade_id=data.cidade_id,
        grupo=data.grupo,
        fuso=data.fuso,
    )
    session.add(loc)
    await session.flush()

    for icao in data.icaos:
        session.add(LocEspIcao(loc_esp_id=loc.id, icao=icao))

    await session.flush()
    await session.refresh(loc, ['cidade', 'icaos'])

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='create',
        resource=RESOURCE_GLE,
        resource_id=loc.id,
        before=None,
        after=_snapshot(loc),
    )

    saida = _to_out(loc)
    await session.commit()
    return success_response(
        data=saida,
        message='Localidade especial criada com sucesso',
    )


@router.put(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[LocEspOut],
    dependencies=[UpdateGle],
)
async def update_localidade(
    id: LocEspId,
    data: LocEspUpdate,
    session: Session,
    current_user: CurrentUser,
) -> ApiResponse[LocEspOut]:
    """Atualiza a localidade. Os ICAOs enviados substituem os atuais."""
    loc = await session.scalar(
        select(GrupoLocEsp)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .where(GrupoLocEsp.id == id)
    )
    if not loc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Localidade não encontrada',
        )

    before = _snapshot(loc)

    await _assert_cidade_existe(session, data.cidade_id)
    await _assert_cidade_livre(session, data.cidade_id, excluir_id=id)
    await _assert_icaos_livres(session, data.icaos, excluir_id=id)

    loc.cidade_id = data.cidade_id
    loc.grupo = data.grupo
    loc.fuso = data.fuso

    atuais = {item.icao for item in loc.icaos}
    novos = set(data.icaos)
    if atuais != novos:
        removidos = atuais - novos
        if removidos:
            await session.execute(
                sa_delete(LocEspIcao).where(
                    LocEspIcao.loc_esp_id == id,
                    LocEspIcao.icao.in_(removidos),
                )
            )
        for icao in sorted(novos - atuais):
            session.add(LocEspIcao(loc_esp_id=id, icao=icao))
        await session.flush()

    await session.refresh(loc, ['cidade', 'icaos'])
    after = _snapshot(loc)

    if before != after:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE_GLE,
            resource_id=loc.id,
            before=before,
            after=after,
        )

    saida = _to_out(loc)
    await session.commit()
    return success_response(
        data=saida,
        message='Localidade especial atualizada com sucesso',
    )


@router.delete(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
    dependencies=[DeleteGle],
)
async def delete_localidade(
    id: LocEspId, session: Session, current_user: CurrentUser
) -> ApiResponse[None]:
    """Remove a localidade. Os ICAOs vao junto (CASCADE no banco)."""
    loc = await session.scalar(
        select(GrupoLocEsp)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .where(GrupoLocEsp.id == id)
    )
    if not loc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Localidade não encontrada',
        )

    before = _snapshot(loc)
    await session.delete(loc)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='delete',
        resource=RESOURCE_GLE,
        resource_id=id,
        before=before,
        after=None,
    )

    await session.commit()
    return success_response(message='Localidade especial removida com sucesso')
