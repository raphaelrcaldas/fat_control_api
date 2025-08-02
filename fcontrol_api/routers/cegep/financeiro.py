from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.missoes import FragMisSchema, UserFragMis
from fcontrol_api.services.financeiro import cache_diarias, cache_soldos
from fcontrol_api.utils.financeiro import custo_missao

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
        stmt = stmt.where(FragMis.afast <= fim)

    result = await session.execute(stmt)
    result: list[tuple[UserFrag, FragMis]] = result.all()

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
    for usr_frg, missao in result:
        usr_frg = UserFragMis.model_validate(usr_frg).model_dump(
            exclude={'user_id', 'frag_id'}
        )
        mis = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )
        mis = custo_missao(
            usr_frg['p_g'],
            usr_frg['sit'],
            mis,
            grupos_pg,
            grupos_cidade,
            valores_cache,
            soldos_cache,
        )

        response.append({
            'user_mis': usr_frg,
            'missao': mis,
        })

    return response
