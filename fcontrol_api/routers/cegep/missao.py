from datetime import date, datetime, time
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from fcontrol_api.schemas.missoes import (
    FragMisSchema,
    PernoiteFragMis,
    UserFragMis,
)
from fcontrol_api.services.comis import verificar_usrs_nao_comiss
from fcontrol_api.services.missao import adicionar_missao, verificar_conflitos

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/missoes', tags=['CEGEP'])


@router.get('/', response_model=list[FragMisSchema])
async def get_fragmentos(session: Session, ini: date, fim: date):
    ini = datetime.combine(ini, time(0, 0, 0))
    fim = datetime.combine(fim, time(23, 59, 59))

    stmt = (
        select(FragMis)
        .options(selectinload(FragMis.users))
        .filter(FragMis.afast >= ini, FragMis.afast <= fim)
        .order_by(FragMis.afast)
    )
    db_frags = await session.scalars(stmt)

    return db_frags.all()


@router.post('/')
async def create_or_update_missao(payload: FragMisSchema, session: Session):
    missao = await adicionar_missao(payload, session)

    await verificar_conflitos(payload, session)

    await verificar_usrs_nao_comiss(
        [u for u in payload.users if u.sit == 'c'], session
    )

    # Adiciona pernoites
    for p in payload.pernoites:
        pnt_data = PernoiteFragMis.model_validate(p).model_dump(
            exclude={'cidade'}
        )
        missao.pernoites.append(PernoiteFrag(**pnt_data))

    # Verifica se os militares constam em outras missões conflitantes

    # Adiciona militares
    for u in payload.users:
        user_data = UserFragMis.model_validate(u).model_dump(
            exclude={'user', 'id'}
        )
        missao.users.append(UserFrag(**user_data))

    await session.commit()
    await session.refresh(missao)

    return {'detail': 'Missão salva com sucesso'}


@router.delete('/{id}')
async def delete_fragmis(id: int, session: Session):
    db_frag = await session.scalar(select(FragMis).where((FragMis.id == id)))
    if not db_frag:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Missão não encontrada',
        )

    await session.execute(
        delete(PernoiteFrag).where(PernoiteFrag.frag_id == id)
    )
    await session.execute(delete(UserFrag).where(UserFrag.frag_id == id))

    await session.delete(db_frag)
    await session.commit()

    return {'detail': 'Missão removida com sucesso'}
