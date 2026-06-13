from datetime import date
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.cegep.missoes import (
    Etiqueta,
    FragEtiqueta,
    FragMis,
    PernoiteFrag,
    UserFrag,
)
from fcontrol_api.schemas.cegep.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.schemas.cegep.missoes import FragMisSchema
from fcontrol_api.services.comis import (
    localizar_comiss_por_missao,
    recalcular_cache_comiss,
)
from fcontrol_api.services.custos import (
    calcular_custos_frag_mis,
    carregar_caches_custo,
    verificar_integridade_custos,
)


async def verificar_conflitos(payload: FragMisSchema, session: AsyncSession):
    user_ids = [u.user_id for u in payload.users]
    if not user_ids:
        return

    afast_date = payload.afast.date()
    regres_date = payload.regres.date()

    # O payload encerra com meia diária no dia do regresso?
    check_md_ult_pnt = any(
        p.meia_diaria and p.data_fim == regres_date for p in payload.pernoites
    )

    # Agrega conflitos por (missão, militar), acumulando os motivos para
    # evitar linhas repetidas quando a missão tem vários pernoites.
    conflitos: dict[tuple[int, int], dict] = {}

    def _registrar(uf: UserFrag, fm: FragMis, motivo: str):
        chave = (fm.id, uf.user_id)
        item = conflitos.setdefault(
            chave, {'uf': uf, 'fm': fm, 'motivos': set()}
        )
        item['motivos'].add(motivo)

    # (1) Sobreposição de datas — independe de a missão ter pernoites.
    overlap_query = (
        select(UserFrag, FragMis)
        .join(FragMis, FragMis.id == UserFrag.frag_id)
        .options(selectinload(UserFrag.user))
        .where(
            UserFrag.user_id.in_(user_ids),
            FragMis.afast < payload.regres,
            payload.afast < FragMis.regres,
        )
    )
    if payload.id:
        overlap_query = overlap_query.where(FragMis.id != payload.id)

    for uf, fm in (await session.execute(overlap_query)).all():
        _registrar(uf, fm, 'sobreposição de datas')

    # (2) Conflitos de meia diária adjacente — dependem dos pernoites.
    md_conds = [
        and_(
            PernoiteFrag.meia_diaria,
            PernoiteFrag.data_fim == afast_date,
        )
    ]
    if check_md_ult_pnt:
        md_conds.append(PernoiteFrag.data_ini == regres_date)

    md_query = (
        select(UserFrag, FragMis, PernoiteFrag)
        .join(FragMis, FragMis.id == UserFrag.frag_id)
        .join(PernoiteFrag, PernoiteFrag.frag_id == FragMis.id)
        .options(selectinload(UserFrag.user))
        .where(
            UserFrag.user_id.in_(user_ids),
            or_(*md_conds),
        )
    )
    if payload.id:
        md_query = md_query.where(FragMis.id != payload.id)

    for uf, fm, pn in (await session.execute(md_query)).all():
        if pn.meia_diaria and pn.data_fim == afast_date:
            _registrar(uf, fm, 'afastamento em conflito com meia diária')
        if check_md_ult_pnt and pn.data_ini == regres_date:
            _registrar(uf, fm, 'meia diária em conflito com o afastamento')

    if not conflitos:
        return

    msg = '\nVerifique o seguinte conflito:'
    for item in conflitos.values():
        uf, fm = item['uf'], item['fm']
        motivo_txt = ' / '.join(sorted(item['motivos']))
        row = (
            f'\n - {fm.tipo_doc} {fm.n_doc} '
            f'{uf.user.p_g} {uf.user.nome_guerra} -> {motivo_txt}'
        ).upper()
        msg += row

    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail=msg,
    )


async def adicionar_missao(
    payload: FragMisSchema, session: AsyncSession, active_org: str
) -> FragMis:
    if payload.id:
        # Atualização (escopada: missão de outra org -> 404)
        missao: FragMis = await session.scalar(
            select(FragMis)
            .options(selectinload(FragMis.etiquetas))
            .filter(FragMis.id == payload.id, FragMis.uae == active_org)
        )
        if not missao:
            raise HTTPException(
                status_code=404, detail='Missão não encontrada'
            )

        missao.desc = payload.desc
        missao.tipo = payload.tipo
        missao.afast = payload.afast
        missao.regres = payload.regres
        missao.indenizavel = payload.indenizavel
        missao.n_doc = payload.n_doc
        missao.tipo_doc = payload.tipo_doc
        missao.obs = payload.obs
        missao.acrec_desloc = payload.acrec_desloc

        await session.execute(
            delete(PernoiteFrag).where(PernoiteFrag.frag_id == missao.id)
        )
        await session.execute(
            delete(UserFrag).where(UserFrag.frag_id == missao.id)
        )
        await session.execute(
            delete(FragEtiqueta).where(FragEtiqueta.frag_id == missao.id)
        )
        # Expira apenas relacionamentos (não colunas escalares como id),
        # para evitar lazy-load síncrono em contexto async ao acessar
        # missao.id mais adiante, mas garantindo que o ORM descarte as
        # coleções obsoletas (cascade delete-orphan) antes do commit.
        session.expire(missao, ['pernoites', 'users', 'etiquetas'])

    else:
        # Criação
        missao = FragMis(
            desc=payload.desc,
            tipo=payload.tipo,
            afast=payload.afast,
            regres=payload.regres,
            indenizavel=payload.indenizavel,
            n_doc=payload.n_doc,
            tipo_doc=payload.tipo_doc,
            obs=payload.obs,
            acrec_desloc=payload.acrec_desloc,
            uae=active_org,
        )
        session.add(missao)
        await session.flush()

    # Processar etiquetas via tabela de associacao
    # Evita lazy load que causa MissingGreenlet em contexto async
    if payload.etiquetas:
        etiqueta_ids = [e.id for e in payload.etiquetas if e.id]
        if etiqueta_ids:
            # Verifica se etiquetas existem (somente da org ativa)
            db_etiquetas = (
                await session.scalars(
                    select(Etiqueta).where(
                        Etiqueta.id.in_(etiqueta_ids),
                        Etiqueta.uae == active_org,
                    )
                )
            ).all()
            # Insere diretamente na tabela de associacao
            for etiqueta in db_etiquetas:
                session.add(
                    FragEtiqueta(
                        frag_id=missao.id,
                        etiqueta_id=etiqueta.id,
                    )
                )

    return missao


def _inputs_custo(
    missao: FragMis,
    users_frag: list[UserFrag],
    pernoites: list[PernoiteFrag],
) -> tuple[
    CustoFragMisInput,
    list[CustoUserFragInput],
    list[CustoPernoiteInput],
]:
    """Converte os objetos ORM da missão nos schemas validados de input de
    custo. Fonte única usada tanto pelo cálculo/gravação do cache quanto
    pela verificação de integridade — assim ambos derivam o hash da mesma
    representação canônica e não divergem."""
    frag_mis_input = CustoFragMisInput(acrec_desloc=missao.acrec_desloc)
    users_input = [
        CustoUserFragInput(p_g=uf.p_g, sit=uf.sit) for uf in users_frag
    ]
    pernoites_input = [
        CustoPernoiteInput(
            id=pnt.id,
            data_ini=pnt.data_ini,
            data_fim=pnt.data_fim,
            meia_diaria=pnt.meia_diaria,
            acrec_desloc=pnt.acrec_desloc,
            cidade_codigo=pnt.cidade_id,
        )
        for pnt in pernoites
    ]
    return frag_mis_input, users_input, pernoites_input


def aplicar_custos_missao(
    missao: FragMis,
    users_frag: list[UserFrag],
    pernoites: list[PernoiteFrag],
    caches: tuple,
) -> None:
    """Calcula e grava o JSONB `custos` da missão a partir de seus
    militares e pernoites (objetos ORM) e dos caches de referência."""
    valores_cache, soldos_cache, grupos_pg, grupos_cidade = caches

    frag_mis_input, users_input, pernoites_input = _inputs_custo(
        missao, users_frag, pernoites
    )

    missao.custos = calcular_custos_frag_mis(
        frag_mis_input,
        users_input,
        pernoites_input,
        grupos_pg,
        grupos_cidade,
        valores_cache,
        soldos_cache,
    )


def verificar_integridade_missao(missao: FragMis) -> bool:
    """True se o cache de custos da missão está íntegro frente aos seus
    militares e pernoites atuais (fase 1: inputs locais).

    Requer `missao.users` e `missao.pernoites` já carregados na instância.
    """
    frag_mis_input, users_input, pernoites_input = _inputs_custo(
        missao, missao.users, missao.pernoites
    )
    return verificar_integridade_custos(
        frag_mis_input, users_input, pernoites_input, missao.custos
    )


async def sincronizar_custos_missao(
    missao: FragMis,
    users_frag: list[UserFrag],
    pernoites: list[PernoiteFrag],
    session: AsyncSession,
    active_org: str,
    footprints_antigos: tuple[tuple[int, date, date], ...] = (),
) -> None:
    """Ponto único de invalidação após criar/atualizar uma missão.

    Recalcula o cache de custos da missão e, em seguida, o cache de todos
    os comissionamentos afetados — tanto pela situação nova (militares
    sit='c' com as datas atuais) quanto pelos footprints antigos
    informados (militares/datas removidos numa edição). Assim nenhum
    caminho de escrita precisa lembrar de invalidar os dois níveis.
    """
    caches = await carregar_caches_custo(session)
    aplicar_custos_missao(missao, users_frag, pernoites, caches)

    afast = missao.afast.date()
    regres = missao.regres.date()

    footprints: list[tuple[int, date, date]] = list(footprints_antigos)
    footprints.extend(
        (uf.user_id, afast, regres) for uf in users_frag if uf.sit == 'c'
    )

    comiss_ids: set[int] = set()
    for user_id, f_afast, f_regres in footprints:
        comiss_ids.update(
            await localizar_comiss_por_missao(
                user_id, f_afast, f_regres, session, uae=active_org
            )
        )

    for comiss_id in comiss_ids:
        await recalcular_cache_comiss(comiss_id, session)


async def recalcular_custos_missoes(
    data_inicio: date,
    data_fim: date | None,
    session: AsyncSession,
) -> dict:
    """
    Recalcula custos de missoes com pernoites no periodo.
    Depois recalcula comissionamentos afetados (apenas sit='c').
    Retorna contagem de missoes e comissionamentos recalculados.
    """
    # 1. Buscar missoes afetadas via pernoites no periodo
    query = (
        select(FragMis)
        .join(PernoiteFrag, PernoiteFrag.frag_id == FragMis.id)
        .where(PernoiteFrag.data_fim >= data_inicio)
    )
    if data_fim is not None:
        query = query.where(PernoiteFrag.data_ini <= data_fim)

    query = query.distinct()

    result = await session.scalars(query)
    missoes: list[FragMis] = list(result.all())

    if not missoes:
        return {'missoes': 0, 'comissionamentos': 0}

    # 2. Carregar caches de referencia (1x so)
    caches = await carregar_caches_custo(session)

    # 3. Set para coletar comissionamentos afetados
    comiss_ids: set[int] = set()

    for missao in missoes:
        # Carregar users (lazy='noload', precisa query explicita)
        users_result = await session.scalars(
            select(UserFrag).where(UserFrag.frag_id == missao.id)
        )
        users_frag = list(users_result.all())

        # Pernoites ja vem via selectin
        pernoites = missao.pernoites

        if not users_frag or not pernoites:
            continue

        aplicar_custos_missao(missao, users_frag, pernoites, caches)

        # Coletar comissionamentos afetados
        afast_date = missao.afast.date()
        regres_date = missao.regres.date()
        for uf in users_frag:
            if uf.sit == 'c':
                ids = await localizar_comiss_por_missao(
                    uf.user_id,
                    afast_date,
                    regres_date,
                    session,
                    uae=missao.uae,
                )
                comiss_ids.update(ids)

    # 4. Recalcular comissionamentos afetados
    for comiss_id in comiss_ids:
        await recalcular_cache_comiss(comiss_id, session)

    await session.flush()

    return {
        'missoes': len(missoes),
        'comissionamentos': len(comiss_ids),
    }
