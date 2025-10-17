from datetime import date, datetime, time
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.schemas.missoes import UserFragMis


async def verificar_usrs_comiss(
    users: list[UserFragMis],
    afast: datetime,
    regres: datetime,
    session: AsyncSession,
) -> None:
    """
    Recebe uma lista de usuários na missão e
    verifica se os mesmos estão comissionados e
    se a data da missão está contida na data do
    comissionamento
    """
    # procura comissionamentos abertos dos usuários envolvidos na missão
    query_comiss = select(Comissionamento).where(
        Comissionamento.user_id.in_([u.user_id for u in users])
    )
    result_comiss = (await session.scalars(query_comiss)).all()

    user_no_comiss: list[UserFragMis] = []
    user_no_mis: list[UserFragMis] = []
    for uf in users:
        # todos os comissionamentos abertos deste usuário
        comiss_for_user = [c for c in result_comiss if c.user_id == uf.user_id]

        # se não houver comissionamento aberto para o usuário
        if not comiss_for_user:
            user_no_comiss.append(uf)
            continue

        # verifica se a missão está contida no intervalo do comissionamento
        comiss = comiss_for_user[0]
        comiss_data_ab = datetime.combine(comiss.data_ab, time(0, 0, 0))
        comiss_data_fc = datetime.combine(comiss.data_fc, time(23, 59, 59))
        if not (comiss_data_ab <= afast and regres <= comiss_data_fc):
            user_no_mis.append(uf)

    if user_no_mis or user_no_comiss:
        msg_parts = []
        if user_no_comiss:
            msg = '\nOs seguintes militares não estão comissionados:'
            for uf in user_no_comiss:
                row = f'\n - {uf.user.p_g} {uf.user.nome_guerra}'.upper()
                msg += row
            msg_parts.append(msg)

        if user_no_mis:
            msg = (
                '\nOs seguintes militares não têm comissionamento '
                'cobrindo o período da missão:'
            )
            for uf in user_no_mis:
                msg += f'\n - {uf.user.p_g} {uf.user.nome_guerra}'.upper()
            msg_parts.append(msg)

        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='\n\n'.join(msg_parts),
        )


async def verificar_conflito_comiss(
    user_id: int,
    data_ab: date,
    data_fc: date,
    session: AsyncSession,
    comiss_id: int = None,
):
    query = select(Comissionamento).where(
        and_(
            (Comissionamento.user_id == user_id),
            (Comissionamento.data_ab <= data_fc),
            (data_ab <= Comissionamento.data_fc),
        )
    )

    if comiss_id:
        query = query.where(Comissionamento.id != comiss_id)

    comiss_conflict = await session.scalar(query)
    if comiss_conflict:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento em conflito de datas para este usuário',
        )
