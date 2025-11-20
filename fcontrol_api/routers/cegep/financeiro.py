from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.missoes import FragMisSchema, UserFragMis
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
    user_id: int = None,
    tipo: str = None,
    ini: date = None,
    fim: date = None,
):
    stmt = (
        select(UserFrag, FragMis)
        .join(FragMis, (FragMis.id == UserFrag.frag_id))
        .join(User, (User.id == UserFrag.user_id))
        .order_by(FragMis.afast.desc())
    )

    if tipo_doc:
        stmt = stmt.where(FragMis.tipo_doc == tipo_doc)

    if n_doc:
        stmt = stmt.where(FragMis.n_doc == n_doc)

    if sit:
        if sit.startswith('!'):
            stmt = stmt.where(UserFrag.sit != sit[1:])
        else:
            stmt = stmt.where(UserFrag.sit == sit)

    if user_id:
        stmt = stmt.where(UserFrag.user_id == user_id).limit(25)

    if user:
        stmt = stmt.where(
            User.nome_guerra.ilike(f'%{user}%')
            | User.nome_completo.ilike(f'%{user}%')
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

    response = []
    for usr_frg, missao in result:
        uf_data = UserFragMis.model_validate(usr_frg).model_dump(
            exclude={'user_id', 'frag_id'}
        )
        mis = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )
        # Read costs from JSONB column (pre-calculated)
        mis = custo_missao(
            uf_data['p_g'],
            uf_data['sit'],
            mis,
        )

        response.append({
            'user_mis': uf_data,
            'missao': mis,
        })

    return response
