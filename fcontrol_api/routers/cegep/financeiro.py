from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.missoes import FragMisSchema, UserFragMis
from fcontrol_api.services.financeiro import cache_diarias, cache_soldos
from fcontrol_api.utils.datas import listar_datas_entre
from fcontrol_api.utils.financeiro import (
    buscar_soldo_por_dia,
    buscar_valor_por_dia,
)

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/financeiro', tags=['CEGEP'])


@router.get('/pgts')
async def get_pgto(
    session: Session,
    tipo_doc: str = None,
    n_doc: int = None,
    sit: str = None,
    user: str = None,
    tipo: str = None,
    ini: date = None,
    fim: date = None,
):
    stmt = (
        select(UserFrag, FragMis)
        .join(FragMis, (FragMis.id == UserFrag.frag_id))
        .join(User, (User.id == UserFrag.user_id))
    )

    if tipo_doc:
        stmt = stmt.where(FragMis.tipo_doc == tipo_doc)

    if n_doc:
        stmt = stmt.where(FragMis.n_doc == n_doc)

    if sit:
        stmt = stmt.where(UserFrag.sit == sit)

    if user:
        stmt = stmt.where(
            User.nome_guerra.ilike(f'%{user}%')
            | User.nome_guerra.ilike(f'%{user}%')
        )

    if tipo:
        stmt = stmt.where(FragMis.tipo == tipo)

    if ini:
        ini = datetime.combine(ini, time(0, 0, 0))
        stmt = stmt.where(FragMis.afast >= ini)

    if fim:
        fim = datetime.combine(fim, time(23, 59, 59))
        stmt = stmt.where(FragMis.regres <= fim)

    result = await session.execute(stmt)

    user_mis: list[tuple[UserFrag, FragMis]] = result.all()

    # Cache de valores de diária por grupo
    valores_cache = await cache_diarias(session)

    # Cache de valores de soldo
    soldos_cache = await cache_soldos(session)

    # Cache de grupos
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

    response = []
    for usr_frg, missao in user_mis:
        grupo_pg = grupos_pg.get(usr_frg.p_g)
        usr = UserFragMis.model_validate(usr_frg).model_dump(
            exclude={'user_id', 'frag_id'}
        )
        mis = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users', 'id'}
        )

        item = {
            **usr,
            **mis,
            'gp_pg': grupo_pg,
            'dias': 0,
            'diarias': 0,
            'valor_total': 0,
            'qtd_acres_desloc': 0,
        }

        pernoites: list[PernoiteFrag] = item['pernoites']
        for pnt in pernoites:
            grupo_cidade = grupos_cidade.get(pnt['cidade_id'], 3)
            pnt['gp_cid'] = grupo_cidade
            pnt['diarias'] = 0
            pnt['subtotal'] = 0

            dias = listar_datas_entre(pnt['data_ini'], pnt['data_fim'])
            for dia in dias[:-1]:
                valor_dia: float
                if item['sit'] == 'g':
                    valor_soldo = buscar_soldo_por_dia(
                        item['p_g'], dia, soldos_cache
                    )
                    valor_dia = valor_soldo * 0.02  # 2% do soldo
                else:
                    valor_dia = buscar_valor_por_dia(
                        grupo_pg, grupo_cidade, dia, valores_cache
                    )
                    pnt['diarias'] += 1

                pnt['subtotal'] += valor_dia

            if item['sit'] == 'g':
                continue

            if pnt['meia_diaria']:
                valor_ultimo = buscar_valor_por_dia(
                    grupo_pg,
                    grupo_cidade,
                    pnt['data_fim'].date(),
                    valores_cache,
                )
                pnt['diarias'] += 0.5
                pnt['subtotal'] += valor_ultimo * 0.5

            if pnt['acrec_desloc']:
                pnt['subtotal'] += 95
                item['qtd_acres_desloc'] += 1

        item['dias'] = len(listar_datas_entre(item['afast'], item['regres']))
        item['diarias'] = sum(list(map(lambda x: x['diarias'], pernoites)))
        item['valor_total'] = sum(
            list(map(lambda x: x['subtotal'], pernoites))
        )

        response.append(item)

    return response
