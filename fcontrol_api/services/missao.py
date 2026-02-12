from datetime import date
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
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
from fcontrol_api.services.financeiro import cache_diarias, cache_soldos
from fcontrol_api.utils.financeiro import calcular_custos_frag_mis


async def verificar_conflitos(payload: FragMisSchema, session: AsyncSession):
    afast_date = payload.afast.date()
    regres_date = payload.regres.date()

    check_md_ult_pnt: bool
    try:
        ult_pnt = list(
            filter(
                lambda p: p.data_fim == regres_date,
                payload.pernoites,
            )
        )[0]
        check_md_ult_pnt = ult_pnt.meia_diaria
    except IndexError:
        check_md_ult_pnt = False

    query_conf = (
        select(UserFrag, FragMis, PernoiteFrag)
        .join(
            FragMis,
            FragMis.id == UserFrag.frag_id,
        )
        .join(
            PernoiteFrag,
            PernoiteFrag.frag_id == FragMis.id,
        )
        .options(selectinload(UserFrag.user))
        .where(
            and_(
                UserFrag.user_id.in_([u.user_id for u in payload.users]),
                or_(
                    and_(
                        FragMis.afast < payload.regres,
                        payload.afast < FragMis.regres,
                    ),
                    or_(
                        and_(
                            PernoiteFrag.meia_diaria,
                            PernoiteFrag.data_fim == afast_date,
                        ),
                        and_(
                            check_md_ult_pnt,
                            PernoiteFrag.data_ini == regres_date,
                        ),
                    ),
                ),
            )
        )
    )

    if payload.id:
        query_conf = query_conf.where(FragMis.id != payload.id)

    result = await session.execute(query_conf)
    conflitos: list[tuple[UserFrag, FragMis, PernoiteFrag]] = result.all()

    if conflitos:
        msg = '\nVerifique o seguinte conflito:'
        for uf, fm, pn in conflitos:
            c1 = (fm.afast < payload.regres) and (payload.afast < fm.regres)
            c2 = bool(pn.meia_diaria and pn.data_fim == afast_date)
            c3 = bool(check_md_ult_pnt and pn.data_ini == regres_date)

            motivo = []
            if c1:
                motivo.append('sobreposição de datas')
            if c2:
                motivo.append('afastamento em conflito com meia diária')
            if c3:
                motivo.append('meia diária em conflito com o afastamento')

            motivo_txt = (
                ' / '.join(motivo) if motivo else 'condição desconhecida'
            )

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
    payload: FragMisSchema, session: AsyncSession
) -> FragMis:
    if payload.id:
        # Atualização
        missao: FragMis = await session.scalar(
            select(FragMis)
            .options(selectinload(FragMis.etiquetas))
            .filter(FragMis.id == payload.id)
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
        )
        session.add(missao)
        await session.flush()

    # Processar etiquetas via tabela de associacao
    # Evita lazy load que causa MissingGreenlet em contexto async
    if payload.etiquetas:
        etiqueta_ids = [e.id for e in payload.etiquetas if e.id]
        if etiqueta_ids:
            # Verifica se etiquetas existem
            db_etiquetas = (
                await session.scalars(
                    select(Etiqueta).where(Etiqueta.id.in_(etiqueta_ids))
                )
            ).all()
            # Insere diretamente na tabela de associacao
            for etiqueta in db_etiquetas:
                session.add(FragEtiqueta(
                    frag_id=missao.id,
                    etiqueta_id=etiqueta.id,
                ))

    return missao


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
    valores_cache = await cache_diarias(session)
    soldos_cache = await cache_soldos(session)

    grupos_pg = dict(
        (
            await session.execute(
                select(GrupoPg.pg_short, GrupoPg.grupo)
            )
        ).all()
    )
    grupos_cidade = dict(
        (
            await session.execute(
                select(GrupoCidade.cidade_id, GrupoCidade.grupo)
            )
        ).all()
    )

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

        # Montar inputs validados
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

        users_input = [
            CustoUserFragInput(p_g=uf.p_g, sit=uf.sit)
            for uf in users_frag
        ]

        if not users_input or not pernoites_input:
            continue

        frag_mis_input = CustoFragMisInput(
            acrec_desloc=missao.acrec_desloc,
        )

        # Calcular custos
        custos = calcular_custos_frag_mis(
            frag_mis_input,
            users_input,
            pernoites_input,
            grupos_pg,
            grupos_cidade,
            valores_cache,
            soldos_cache,
        )

        missao.custos = custos

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
