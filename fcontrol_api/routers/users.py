from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.enums.especialidade import EspecialidadeEnum
from fcontrol_api.enums.quadro import QuadroEnum
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User, UserPromo
from fcontrol_api.schemas.response import ApiPaginatedResponse, ApiResponse
from fcontrol_api.schemas.users import (
    PwdSchema,
    UserFull,
    UserProfile,
    UserPromoCreate,
    UserPromoPublic,
    UserPublic,
    UserSchema,
    UserUpdate,
)
from fcontrol_api.security import (
    ActiveOrg,
    ActiveOrgOptional,
    ensure_org_permission_or_owner,
    get_current_user,
    get_password_hash,
    permission_checker,
    require_admin,
)
from fcontrol_api.services.auth import get_user_roles, list_user_orgs
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.users import (
    check_user_conflicts,
    validate_promo_hierarchy,
)
from fcontrol_api.settings import Settings
from fcontrol_api.utils.responses import paginated_response, success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/users', tags=['users'])


def _ensure_user_in_active_org(
    db_user: User, active_org: str | None, requester: User
) -> None:
    """Bloqueia acesso a usuário de outra unidade (escopo por org ativa).

    Fora do contexto Sistema (`active_org` NULL), o alvo precisa pertencer à
    org ativa. O próprio usuário (self-service) é sempre exceção. Cross-org
    responde 404 para não revelar a existência do registro em outra unidade.
    """
    if requester.id == db_user.id:
        return
    if active_org is not None and db_user.unidade != active_org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )


@router.get('/me', response_model=ApiResponse[UserProfile])
async def read_users_me(
    request: Request,
    session: Session,
    current_user: CurrentUser,
):
    active_org = getattr(request.state, 'active_org', None)
    app_client = getattr(request.state, 'app_client', None)
    permissions = await get_user_roles(
        current_user.id, session, active_org, app_client
    )

    # Escopos de org disponíveis: vínculos (fatcontrol) ou lotações de
    # tripulante (fatbird). A fonte depende do cliente OAuth do token.
    orgs = await list_user_orgs(current_user.id, session, app_client)

    profile = UserProfile(
        id=current_user.id,
        posto=current_user.p_g,
        nome_guerra=current_user.nome_guerra,
        role=permissions.get('role'),
        permissions=permissions.get('perms', []),
        active_org=active_org,
        orgs=orgs,
    )

    return success_response(data=profile)


@router.post('/change-pwd', response_model=ApiResponse[None])
async def change_pwd(
    pwd_schema: PwdSchema,
    session: Session,
    current_user: CurrentUser,
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

    return success_response(message='Senha alterada com sucesso')


@router.post('/reset-pwd', response_model=ApiResponse[None])
async def reset_pwd(
    user_id: int,
    session: Session,
    active_org: ActiveOrgOptional,
    current_user: Annotated[User, Depends(require_admin)],
):
    db_user = await session.scalar(select(User).where(User.id == user_id))
    if not db_user:
        # 404 (não 400) para não diferenciar "não existe" de "outra org"
        # — mesmo status do guard abaixo, sem oráculo de enumeração.
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuario nao encontrado',
        )

    # Admin de unidade só reseta senha de usuário da própria org ativa.
    _ensure_user_in_active_org(db_user, active_org, current_user)

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

    return success_response(message='Senha resetada com sucesso')


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[UserPublic],
)
async def create_user(
    payload: UserSchema,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, Depends(permission_checker('user', 'create'))],
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
        quadro=payload.quadro,
        esp=payload.esp,
        nome_guerra=payload.nome_guerra,
        nome_completo=payload.nome_completo,
        ult_promo=payload.ult_promo,
        id_fab=payload.id_fab,
        saram=payload.saram,
        cpf=payload.cpf,
        nasc=payload.nasc,
        data_praca=payload.data_praca,
        email_pess=payload.email_pess,
        email_fab=payload.email_fab,
        telefone=payload.telefone,
        # Unidade não vem do payload: o usuário é sempre cadastrado na
        # organização ativa de quem o cria (escopo por org).
        unidade=active_org,
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
    await session.refresh(db_user, ['posto'])

    return success_response(
        data=UserPublic.model_validate(db_user),
        message='Usuario adicionado com sucesso',
    )


@router.get('/', response_model=ApiPaginatedResponse[UserPublic])
async def read_users(
    session: Session,
    active_org: ActiveOrgOptional,
    _: Annotated[User, Depends(permission_checker('user', 'view'))],
    search: str | None = None,
    p_g: str | None = None,
    quadro: QuadroEnum | None = None,
    esp: EspecialidadeEnum | None = None,
    active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 15,
):
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

    # Escopo por org ativa: fora do contexto Sistema, lista apenas os
    # usuários da unidade ativa. Sistema (active_org NULL) vê todas as
    # unidades — mesmo padrão dos vínculos em security/roles.py.
    if active_org is not None:
        filters.append(User.unidade == active_org)

    if search:
        # Busca por nome de guerra OU nome completo
        search_term = f'%{search.strip()}%'
        filters.append(
            or_(
                func.unaccent(User.nome_guerra).ilike(
                    func.unaccent(search_term)
                ),
                func.unaccent(User.nome_completo).ilike(
                    func.unaccent(search_term)
                ),
            )
        )

    if p_g:
        # Suporta múltiplos P/G separados por vírgula
        pg_list = [pg.strip() for pg in p_g.split(',') if pg.strip()]
        if len(pg_list) == 1:
            filters.append(User.p_g == pg_list[0])
        elif len(pg_list) > 1:
            filters.append(User.p_g.in_(pg_list))

    if quadro:
        filters.append(User.quadro == quadro.value)

    if esp:
        filters.append(User.esp == esp.value)

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

    return paginated_response(
        items=[UserPublic.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get('/{user_id}', response_model=ApiResponse[UserFull])
async def get_user(
    user_id: int,
    session: Session,
    active_org: ActiveOrgOptional,
    user: CurrentUser,
):
    query = select(User).where(User.id == user_id)
    db_user = await session.scalar(query)

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )

    _ensure_user_in_active_org(db_user, active_org, user)

    await ensure_org_permission_or_owner(
        user, session, active_org, 'user', 'view', db_user.id
    )

    return success_response(data=UserFull.model_validate(db_user))


@router.put('/{user_id}', response_model=ApiResponse[UserFull])
async def update_user(
    user_id: int,
    user_patch: UserUpdate,
    session: Session,
    active_org: ActiveOrgOptional,
    user: CurrentUser,
):
    db_user = await session.scalar(select(User).where(User.id == user_id))

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )

    _ensure_user_in_active_org(db_user, active_org, user)

    await ensure_org_permission_or_owner(
        user, session, active_org, 'user', 'update', db_user.id
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

    # Invariante: User.active=False ⇒ Tripulante.active=False em toda
    # unidade. O User é diretório global; desativá-lo cascateia para os
    # vínculos operacionais de todas as UAEs, evitando o estado órfão
    # invisível (user inativo + tripulante ativo) que sumiria das telas
    # de quads/escala sem deixar onde corrigir o flag.
    if patch.get('active') is False:
        await session.execute(
            update(Tripulante)
            .where(
                Tripulante.user_id == user_id,
                Tripulante.active.is_(True),
            )
            .values(active=False)
        )

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
    await session.refresh(db_user, ['posto'])

    return success_response(
        data=UserFull.model_validate(db_user),
        message='Usuario atualizado com sucesso',
    )


@router.delete('/{user_id}', response_model=ApiResponse[None])
async def delete_user(
    user_id: int,
    session: Session,
    active_org: ActiveOrgOptional,
    user: Annotated[User, Depends(permission_checker('user', 'delete'))],
):
    db_user = await session.scalar(select(User).where(User.id == user_id))

    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )

    _ensure_user_in_active_org(db_user, active_org, user)

    if db_user.id == user.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Não é possivel deletar o próprio usuario',
        )

    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='user',
        resource_id=db_user.id,
    )

    try:
        await session.delete(db_user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Não é possível excluir o usuário pois ele está'
                ' vinculado a outros registros do sistema'
            ),
        )

    return success_response(message='Usuario deletado com sucesso')


@router.get(
    '/{user_id}/promocoes',
    response_model=ApiResponse[list[UserPromoPublic]],
)
async def list_user_promos(
    user_id: int,
    session: Session,
    active_org: ActiveOrgOptional,
    user: CurrentUser,
):
    db_user = await session.scalar(select(User).where(User.id == user_id))
    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )

    _ensure_user_in_active_org(db_user, active_org, user)

    await ensure_org_permission_or_owner(
        user, session, active_org, 'user', 'view', user_id
    )

    promos = await session.scalars(
        select(UserPromo)
        .where(UserPromo.user_id == user_id)
        .order_by(UserPromo.data_promo.desc(), UserPromo.id.desc())
    )

    return success_response(
        data=[UserPromoPublic.model_validate(p) for p in promos.all()]
    )


@router.post(
    '/{user_id}/promocoes',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[UserPromoPublic],
)
async def create_user_promo(
    user_id: int,
    payload: UserPromoCreate,
    session: Session,
    active_org: ActiveOrgOptional,
    user: Annotated[User, Depends(permission_checker('user', 'update'))],
):
    db_user = await session.scalar(select(User).where(User.id == user_id))
    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )

    _ensure_user_in_active_org(db_user, active_org, user)

    await validate_promo_hierarchy(
        session, user_id, payload.p_g, payload.data_promo
    )

    db_promo = UserPromo(
        user_id=user_id,
        p_g=payload.p_g,
        data_promo=payload.data_promo,
    )
    session.add(db_promo)
    await session.flush()

    await log_user_action(
        session=session,
        user_id=user.id,
        action='create',
        resource='user_promo',
        resource_id=db_promo.id,
        before=None,
        after={
            'user_id': user_id,
            'p_g': payload.p_g.value,
            'data_promo': payload.data_promo.isoformat(),
        },
    )

    await session.commit()
    await session.refresh(db_promo, ['posto'])

    return success_response(
        data=UserPromoPublic.model_validate(db_promo),
        message='Promoção registrada com sucesso',
    )


@router.delete(
    '/{user_id}/promocoes/{promo_id}',
    response_model=ApiResponse[None],
)
async def delete_user_promo(
    user_id: int,
    promo_id: int,
    session: Session,
    active_org: ActiveOrgOptional,
    user: Annotated[User, Depends(permission_checker('user', 'update'))],
):
    db_user = await session.scalar(select(User).where(User.id == user_id))
    if not db_user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Usuario nao encontrado'
        )

    _ensure_user_in_active_org(db_user, active_org, user)

    db_promo = await session.scalar(
        select(UserPromo).where(
            UserPromo.id == promo_id, UserPromo.user_id == user_id
        )
    )
    if not db_promo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Promoção não encontrada',
        )

    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='user_promo',
        resource_id=promo_id,
        before={
            'user_id': user_id,
            'p_g': db_promo.p_g,
            'data_promo': db_promo.data_promo.isoformat(),
        },
        after=None,
    )

    await session.delete(db_promo)
    await session.commit()

    return success_response(message='Promoção removida com sucesso')
