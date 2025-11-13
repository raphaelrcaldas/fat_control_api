from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.users import (
    PwdSchema,
    UserFull,
    UserProfile,
    UserPublic,
    UserSchema,
    UserUpdate,
)
from fcontrol_api.security import get_current_user, get_password_hash
from fcontrol_api.services.auth import get_user_roles
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.users import check_user_conflicts
from fcontrol_api.settings import Settings

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/users', tags=['users'])


@router.get('/me', response_model=UserProfile)
async def read_users_me(
    session: Session, current_user: Annotated[User, Depends(get_current_user)]
):
    permissions = await get_user_roles(current_user.id, session)

    profile = UserProfile(
        id=current_user.id,
        posto=current_user.p_g,
        nome_guerra=current_user.nome_guerra,
        role=permissions.get('role'),
        permissions=permissions.get('perms', []),
    )

    return profile


@router.post('/change-pwd')
async def change_pwd(
    pwd_schema: PwdSchema,
    session: Session,
    current_user: Annotated[User, Depends(get_current_user)],
):
    current_user.first_login = False
    current_user.password = get_password_hash(pwd_schema.new_pwd)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='change-pwd',
        resource='user',
        resource_id=current_user.id,
        before=None,
        after=None,
    )

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

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='reset-pwd',
        resource='user',
        resource_id=user_id,
        before=None,
        after=None,
    )

    await session.commit()

    return {'detail': 'Senha resetada com sucesso!'}


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_user(
    payloadUser: UserSchema,
    session: Session,
    user: User = Depends(get_current_user),
):
    # Verifica conflitos de unicidade
    await check_user_conflicts(
        session,
        saram=payloadUser.saram,
        id_fab=payloadUser.id_fab,
        cpf=payloadUser.cpf,
        email_fab=payloadUser.email_fab,
        email_pess=payloadUser.email_pess,
    )

    hashed_password = get_password_hash(Settings().DEFAULT_USER_PASSWORD)

    db_user = User(
        p_g=payloadUser.p_g,
        esp=payloadUser.esp,
        nome_guerra=payloadUser.nome_guerra,
        nome_completo=payloadUser.nome_completo,
        ult_promo=payloadUser.ult_promo,
        id_fab=payloadUser.id_fab,
        saram=payloadUser.saram,
        cpf=payloadUser.cpf,
        nasc=payloadUser.nasc,
        email_pess=payloadUser.email_pess,
        email_fab=payloadUser.email_fab,
        unidade=payloadUser.unidade,
        ant_rel=payloadUser.ant_rel,
        password=hashed_password,
    )

    session.add(db_user)
    await session.flush()
    await session.refresh(db_user)

    await log_user_action(
        session=session,
        user_id=user.id,
        action='create',
        resource='user',
        resource_id=db_user.id,
        before=None,
        after=None,
    )
    await session.commit()

    return {'detail': 'Usuário Adicionado com sucesso'}


@router.get('/', response_model=list[UserPublic])
async def read_users(session: Session, search: str = None):
    query = select(User)

    if search:
        query = query.where(
            User.nome_guerra.ilike(f'%{search.strip()}%') & User.active
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


@router.put('/{user_id}')
async def update_user(
    user_id: int,
    user_patch: UserUpdate,  # type: ignore
    session: Session,
    user: User = Depends(get_current_user),
):
    db_user = await session.scalar(select(User).where(User.id == user_id))

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='User not found'
        )

    patch = user_patch.model_dump(exclude_unset=True)
    # Verifica conflitos apenas para os campos presentes na atualização
    conflict_keys = {
        k: patch[k]
        for k in ('saram', 'id_fab', 'cpf', 'email_fab', 'email_pess')
        if k in patch
    }
    if conflict_keys:
        await check_user_conflicts(
            session,
            exclude_user_id=user_id,
            **conflict_keys,
        )

    # Captura o estado ANTES da atualização
    before_patch: dict = {}
    for key in patch.keys():
        value = getattr(db_user, key)
        if isinstance(value, (datetime, date)):
            before_patch[key] = value.isoformat()
        else:
            before_patch[key] = value

    # Aplica a atualização no objeto
    for key, value in patch.items():
        setattr(db_user, key, value)

    # Prepara o estado DEPOIS da atualização para o log
    after_patch: dict = {}
    for key, value in patch.items():
        if isinstance(value, (datetime, date)):
            after_patch[key] = value.isoformat()
        else:
            after_patch[key] = value

    await log_user_action(
        session=session,
        user_id=user.id,
        action='patch',
        resource='user',
        resource_id=user_id,
        before=before_patch,
        after=after_patch,
    )

    await session.commit()

    return {'detail': 'Usuário atualizado com sucesso'}


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
