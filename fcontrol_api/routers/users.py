from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models import User
from fcontrol_api.schemas.message import UserMessage
from fcontrol_api.schemas.users import UserPublic, UserSchema
from fcontrol_api.security import get_password_hash
from fcontrol_api.settings import Settings

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/users', tags=['users'])


@router.post('/', status_code=HTTPStatus.CREATED, response_model=UserMessage)
async def create_user(user: UserSchema, session: Session):
    db_user_saram = await session.scalar(
        select(User).where(User.saram == user.saram)
    )
    if db_user_saram:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='SARAM já registrado',
        )

    if user.id_fab:
        db_user_id = await session.scalar(
            select(User).where(User.id_fab == user.id_fab)
        )
        if db_user_id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='ID FAB já registrado',
            )

    if user.cpf:
        db_user_id = await session.scalar(
            select(User).where(User.cpf == user.cpf)
        )
        if db_user_id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='CPF já registrado',
            )

    if user.email_fab:
        db_email_fab = await session.scalar(
            select(User).where(User.email_fab == user.email_fab)
        )
        if db_email_fab:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Zimbra já registrado',
            )

    if user.email_pess:
        db_email_pess = await session.scalar(
            select(User).where(User.email_pess == user.email_pess)
        )
        if db_email_pess:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Email pessoal já registrado',
            )

    hashed_password = get_password_hash(Settings().DEFAULT_USER_PASSWORD)  # type: ignore

    db_user = User(
        p_g=user.p_g,
        esp=user.esp,
        nome_guerra=user.nome_guerra,
        nome_completo=user.nome_completo,
        ult_promo=user.ult_promo,
        id_fab=user.id_fab,
        saram=user.saram,
        cpf=user.cpf,
        nasc=user.nasc,
        email_pess=user.email_pess,
        email_fab=user.email_fab,
        unidade=user.unidade,
        password=hashed_password,
    )  # type: ignore

    await session.add(db_user)  # type: ignore
    await session.commit()
    await session.refresh(db_user)

    return {'detail': 'Usuário Adicionado com sucesso', 'data': db_user}


@router.get('/', response_model=list[UserPublic])
async def read_users(session: Session):
    users = await session.scalars(select(User))

    return users.all()


@router.get('/{user_id}', response_model=UserSchema)
async def get_user(user_id: int, session: Session):
    query = select(User).where(User.id == user_id)
    db_user = await session.scalar(query)

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    return db_user


@router.put('/{user_id}', response_model=UserMessage)
async def update_user(user_id: int, user: UserSchema, session: Session):
    query = select(User).where(User.id == user_id)

    db_user = await session.scalar(query)

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    for key, value in user.model_dump(exclude_unset=True).items():
        setattr(db_user, key, value)

    await session.commit()
    await session.refresh(db_user)

    return {'detail': 'Usuário atualizado com sucesso', 'data': db_user}


# @router.delete('/{user_id}')
# async def delete_user(user_id: int, session: Session):
#     query = await select(User).where(User.id == user_id)

#     db_user = session.scalar(query)

#     if not db_user:
#         raise HTTPException(
#             status_code=HTTPStatus.NOT_FOUND, detail='User not found'
#         )

#     await session.delete(db_user)
#     await session.commit()

#     return {'detail': 'Deletado com Sucesso'}
