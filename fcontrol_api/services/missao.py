from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.cegep.etiquetas import Etiqueta
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from fcontrol_api.schemas.missoes import FragMisSchema


async def verificar_conflitos(payload: FragMisSchema, session: AsyncSession):
    afast_date = payload.afast.date()
    regres_date = payload.regres.date()

    check_md_ult_pnt: bool
    try:
        ult_pnt = list(
            filter(
                lambda p: (p.data_fim == regres_date),
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
            select(FragMis).filter(FragMis.id == payload.id)
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

    # Processar etiquetas
    if payload.etiquetas:
        etiqueta_ids = [e.id for e in payload.etiquetas if e.id]
        if etiqueta_ids:
            db_etiquetas = (
                await session.scalars(
                    select(Etiqueta).where(Etiqueta.id.in_(etiqueta_ids))
                )
            ).all()
            missao.etiquetas = list(db_etiquetas)
    else:
        missao.etiquetas = []

    return missao
