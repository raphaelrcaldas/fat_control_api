from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.users import (
    PwdSchema,
    UserFull,
    UserProfile,
    UserPublicPaginated,
    UserSchema,
    UserUpdate,
)
from fcontrol_api.security import (
    get_current_user,
    get_password_hash,
    permission_checker,
)
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
    payload: UserSchema,
    session: Session,
    user: User = Depends(permission_checker('user', 'create')),
):
    # Verifica conflitos de unicidade
    await check_user_conflicts(
        session,
        saram=payload.saram,
        id_fab=payload.id_fab,
        cpf=payload.cpf,
        email_fab=payload.email_fab,
        email_pess=payload.email_pess,
    )

    hashed_password = get_password_hash(Settings().DEFAULT_USER_PASSWORD)

    db_user = User(
        p_g=payload.p_g,
        esp=payload.esp,
        nome_guerra=payload.nome_guerra,
        nome_completo=payload.nome_completo,
        ult_promo=payload.ult_promo,
        id_fab=payload.id_fab,
        saram=payload.saram,
        cpf=payload.cpf,
        nasc=payload.nasc,
        email_pess=payload.email_pess,
        email_fab=payload.email_fab,
        unidade=payload.unidade,
        ant_rel=payload.ant_rel,
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


@router.get('/', response_model=UserPublicPaginated)
async def read_users(
    session: Session,
    search: str | None = None,
    p_g: str | None = None,
    active: bool | None = None,
    page: int = 1,
    per_page: int = 15,
):
    # Limita per_page para evitar queries muito pesadas
    per_page = min(per_page, 100)
    page = max(page, 1)
    offset = (page - 1) * per_page

    # Query base ordenada (determinística com User.id como critério final)
    base_query = (
        select(User)
        .join(PostoGrad)
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
            User.id,
        )
    )

    # Query de contagem
    count_query = select(func.count()).select_from(User)

    # Aplica filtros
    filters = []

    if search:
        # Busca por nome de guerra OU nome completo
        search_term = f'%{search.strip()}%'
        filters.append(
            or_(
                User.nome_guerra.ilike(search_term),
                User.nome_completo.ilike(search_term),
            )
        )

    if p_g:
        # Suporta múltiplos P/G separados por vírgula
        pg_list = [pg.strip() for pg in p_g.split(',') if pg.strip()]
        if len(pg_list) == 1:
            filters.append(User.p_g == pg_list[0])
        elif len(pg_list) > 1:
            filters.append(User.p_g.in_(pg_list))

    if active is not None:
        filters.append(User.active == active)

    # Aplica todos os filtros
    for f in filters:
        base_query = base_query.where(f)
        count_query = count_query.where(f)

    # Executa count e fetch em paralelo
    total = await session.scalar(count_query) or 0
    users_result = await session.scalars(
        base_query.offset(offset).limit(per_page)
    )
    users = users_result.all()

    # Calcula número de páginas
    pages = (total + per_page - 1) // per_page if total > 0 else 1

    return UserPublicPaginated(
        items=users,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


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
    user_patch: UserUpdate,
    session: Session,
    user: User = Depends(permission_checker('user', 'update')),
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
