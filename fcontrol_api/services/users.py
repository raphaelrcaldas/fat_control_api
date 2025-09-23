from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.public.users import User


async def check_user_conflicts(
    session: AsyncSession,
    saram: int | None = None,
    id_fab: int | None = None,
    cpf: str | None = None,
    email_fab: str | None = None,
    email_pess: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    """
    Verifica conflitos de unicidade no banco.
    Lança HTTPException em caso de conflito.

    Parâmetros opcionais: verifica apenas campos não-None.
    exclude_user_id: quando informado, ignora esse id (útil em updates).
    """
    # SARAM
    if saram:
        q = select(User).where(User.saram == saram)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='SARAM já registrado',
            )

    # ID FAB
    if id_fab:
        q = select(User).where(User.id_fab == id_fab)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='ID FAB já registrado',
            )

    # CPF
    if cpf:
        q = select(User).where(User.cpf == cpf)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='CPF já registrado',
            )

    # EMAIL FAB (Zimbra)
    if email_fab:
        q = select(User).where(User.email_fab == email_fab)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Zimbra já registrado',
            )

    # EMAIL PESSOAL
    if email_pess:
        q = select(User).where(User.email_pess == email_pess)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Email pessoal já registrado',
            )
