from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.message import UserMessage
from fcontrol_api.schemas.users import (
    PwdSchema,
    UserFull,
    UserPublic,
    UserSchema,
)
from fcontrol_api.security import (
    get_current_user,
    get_password_hash,
    verify_password,
)
from fcontrol_api.services.users import check_user_conflicts
from fcontrol_api.settings import Settings

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/users', tags=['users'])


@router.post('/change-pwd')
async def change_pwd(
    pwd_schema: PwdSchema,
    session: Session,
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not verify_password(pwd_schema.prev_pwd, current_user.password):
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Revise suas informações',
        )

    current_user.first_login = False
    current_user.password = get_password_hash(pwd_schema.new_pwd)

    await session.commit()

    return {'detail': 'Senha alterada com sucesso!'}


@router.post('/reset-pwd')
async def reset_pwd(
    user_id: int,
    session: Session,
    current_user: Annotated[User, Depends(get_current_user)],
):
    db_user = await session.scalar(select(User).where(User.id == user_id))
    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='User not found',
        )

    hashed_password = get_password_hash(Settings().DEFAULT_USER_PASSWORD)  # type: ignore
    db_user.first_login = True
    db_user.password = hashed_password

    await session.commit()

    return {'detail': 'Senha resetada com sucesso!'}


@router.post('/', status_code=HTTPStatus.CREATED, response_model=UserMessage)
async def create_user(user: UserSchema, session: Session):
    # Verifica conflitos de unicidade
    await check_user_conflicts(
        session,
        saram=user.saram,
        id_fab=user.id_fab,
        cpf=user.cpf,
        email_fab=user.email_fab,
        email_pess=user.email_pess,
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
        ant_rel=None,
        password=hashed_password,
    )  # type: ignore

    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)

    return {'detail': 'Usuário Adicionado com sucesso', 'data': db_user}


@router.get('/', response_model=list[UserPublic])
async def read_users(session: Session, search: str = None):
    query = select(User)

    if search:
        query = query.where(
            User.nome_guerra.ilike(f'%{search.strip()}%')
        ).limit(10)

    users = await session.scalars(query)

    return users.all()


@router.get('/{user_id}', response_model=UserFull)
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
    db_user = await session.scalar(select(User).where(User.id == user_id))

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    updates = user.model_dump(exclude_unset=True)
    # Verifica conflitos apenas para os campos presentes na atualização
    conflict_keys = {
        k: updates[k]
        for k in (
            'saram', 'id_fab', 'cpf', 'email_fab', 'email_pess'
        )
        if k in updates
    }
    if conflict_keys:
        await check_user_conflicts(
            session,
            exclude_user_id=user_id,
            **conflict_keys,
        )

    for key, value in updates.items():
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
