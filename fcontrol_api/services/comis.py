from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.schemas.missoes import UserFragMis


async def verificar_usrs_nao_comiss(
    users: list[UserFragMis], session: AsyncSession
) -> None:
    """
    Recebe uma lista de usuários na missão e
    verifica se os mesmos estão comissionados
    """
    # procura comissionamento abertos dos usuarios na missao
    query_comiss = select(Comissionamento).where(
        and_(
            Comissionamento.user_id.in_([u.user_id for u in users]),
            Comissionamento.status == 'aberto',
        )
    )
    result_comiss = (await session.scalars(query_comiss)).all()
    ids_comis = [u.user_id for u in result_comiss]

    user_no_comiss: list[UserFragMis] = []
    for uf in users:
        if uf.user_id not in ids_comis:
            user_no_comiss.append(uf)

    # print(users)
    if user_no_comiss:
        msg = '\nOs seguintes militares não estão comissionados:'
        for uf in user_no_comiss:
            row = f'\n - {uf.user.p_g} {uf.user.nome_guerra}'.upper()
            msg += row

        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=msg,
        )
