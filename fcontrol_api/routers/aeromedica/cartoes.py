import asyncio
import logging
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.aeromedica.cartoes import (
    CartaoSaudeCreate,
    CartaoSaudePublic,
    CartaoSaudeUpdate,
    CartaoSaudeWithUser,
    OrfaoAeromedicaPublic,
    OrfaosAeromedicaDelete,
    OrfaosAeromedicaDeleteResponse,
    OrfaosAeromedicaResumo,
    UserCartaoSaude,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    ensure_org_permission_or_owner,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.storage import delete_file
from fcontrol_api.utils.responses import success_response

logger = logging.getLogger(__name__)

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/cartoes-saude', tags=['Aeromedica'])

# Bucket do domínio aeromédica (mesma constante do router de atas) — a
# limpeza de órfãos remove os PDFs das atas junto com os registros.
BUCKET = 'aeromedica'

# Dados de saúde são sensíveis: toda leitura exige 'view' e cada escrita a
# sua ação. Admin da org ativa tem bypass (ver permission_checker).
ViewCartao = Depends(permission_checker('cartoes-saude', 'view'))
CreateCartao = Depends(permission_checker('cartoes-saude', 'create'))
UpdateCartao = Depends(permission_checker('cartoes-saude', 'update'))
DeleteCartao = Depends(permission_checker('cartoes-saude', 'delete'))


@router.get(
    '/',
    response_model=ApiResponse[list[UserCartaoSaude]],
    dependencies=[ViewCartao],
)
async def get_cartoes_saude(
    session: Session,
    active_org: ActiveOrg,
    search: str | None = None,
    p_g: str | None = None,
    funcao: str | None = None,
    tripulante: bool | None = None,
):
    """Lista usuarios com seus cartoes de saude."""
    cemal_tem_ata = (
        exists(
            select(AtaInspecao.id).where(
                AtaInspecao.user_id == User.id,
                AtaInspecao.validade_inspsau == CartaoSaude.cemal,
            )
        )
        .correlate(User, CartaoSaude)
        .label('cemal_tem_ata')
    )

    total_atas = (
        select(func.count(AtaInspecao.id))
        .where(AtaInspecao.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
        .label('total_atas')
    )

    query = (
        select(
            User,
            CartaoSaude,
            Tripulante.id,
            cemal_tem_ata,
            total_atas,
        )
        .join(PostoGrad)
        .outerjoin(
            Tripulante,
            and_(
                Tripulante.user_id == User.id,
                Tripulante.active.is_(True),
                Tripulante.uae == active_org,
            ),
        )
        .outerjoin(
            CartaoSaude,
            CartaoSaude.user_id == User.id,
        )
        .where(
            User.active.is_(True),
            User.unidade == active_org,
        )
    )

    # Escopo por org via User.unidade; o param filtra apenas se o usuario
    # tem vinculo de tripulante ativo.
    if tripulante is True:
        query = query.where(Tripulante.id.isnot(None))
    elif tripulante is False:
        query = query.where(Tripulante.id.is_(None))

    if search:
        safe = (
            search
            .replace('\\', '\\\\')
            .replace('%', '\\%')
            .replace('_', '\\_')
        )
        pattern = f'%{safe}%'
        query = query.where(
            User.nome_guerra.ilike(pattern) | User.nome_completo.ilike(pattern)
        )

    if p_g:
        pgs = [p.strip() for p in p_g.split(',')]
        query = query.where(User.p_g.in_(pgs))

    if funcao:
        funcs = [f.strip() for f in funcao.split(',')]
        query = query.where(Tripulante.func.in_(funcs))

    query = query.order_by(
        PostoGrad.ant.asc(),
        User.ult_promo.asc(),
        User.ant_rel.asc(),
        User.id,
    )

    result = await session.execute(query)
    rows = result.unique().all()

    data = [
        UserCartaoSaude(
            user=row[0],
            cartao=row[1],
            tripulante=row[2] is not None,
            cemal_tem_ata=row[3] if row[1] and row[1].cemal else None,
            total_atas=row[4],
        )
        for row in rows
    ]

    return success_response(data=data)


@router.get(
    '/orfaos',
    response_model=ApiResponse[OrfaosAeromedicaResumo],
    dependencies=[DeleteCartao],
)
async def get_orfaos_aeromedica(session: Session, active_org: ActiveOrg):
    """Documentos aeromédicos de militares inativos da org (limpeza).

    Agrupa por militar: cartão de saúde e/ou atas de inspeção. A exclusão
    (DELETE /orfaos) é conjunta — apaga cartão e atas do militar de uma vez.
    """
    result = await session.execute(
        select(
            User.id,
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            CartaoSaude.id.label('cartao_id'),
            func.count(AtaInspecao.id).label('total_atas'),
            func.coalesce(func.sum(AtaInspecao.file_size), 0).label(
                'atas_size'
            ),
        )
        .outerjoin(CartaoSaude, CartaoSaude.user_id == User.id)
        .outerjoin(AtaInspecao, AtaInspecao.user_id == User.id)
        .where(
            User.active.is_(False),
            User.unidade == active_org,
        )
        .group_by(
            User.id,
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            CartaoSaude.id,
        )
        .having(
            or_(
                CartaoSaude.id.is_not(None),
                func.count(AtaInspecao.id) > 0,
            )
        )
        .order_by(User.nome_guerra, User.id)
    )

    itens = []
    total_cartoes = 0
    total_atas = 0
    atas_size = 0
    for row in result.all():
        total_cartoes += int(row.cartao_id is not None)
        total_atas += row.total_atas
        atas_size += row.atas_size
        itens.append(
            OrfaoAeromedicaPublic(
                user_id=row.id,
                p_g=row.p_g,
                nome_guerra=row.nome_guerra,
                nome_completo=row.nome_completo,
                tem_cartao=row.cartao_id is not None,
                total_atas=row.total_atas,
                atas_size=row.atas_size,
            )
        )

    return success_response(
        data=OrfaosAeromedicaResumo(
            total_militares=len(itens),
            total_cartoes=total_cartoes,
            total_atas=total_atas,
            atas_size=atas_size,
            itens=itens,
        ),
    )


@router.delete(
    '/orfaos',
    response_model=ApiResponse[OrfaosAeromedicaDeleteResponse],
    dependencies=[DeleteCartao],
)
async def delete_orfaos_aeromedica(
    payload: OrfaosAeromedicaDelete,
    session: Session,
    active_org: ActiveOrg,
):
    """Remove cartão E atas dos militares inativos selecionados."""
    users_validos = select(User.id).where(
        User.id.in_(payload.user_ids),
        User.active.is_(False),
        User.unidade == active_org,
    )

    atas = (
        await session.scalars(
            select(AtaInspecao).where(AtaInspecao.user_id.in_(users_validos))
        )
    ).all()
    for ata in atas:
        # Tolera falha ao remover o PDF (ex.: já ausente no storage) para
        # garantir consistência banco↔storage: o registro sai do banco
        # mesmo que o objeto físico não exista mais.
        try:
            await asyncio.to_thread(delete_file, BUCKET, ata.file_path)
        except Exception:
            logger.warning(
                'Falha ao remover arquivo da ata órfã %s (%s)',
                ata.id,
                ata.file_path,
                exc_info=True,
            )
        await session.delete(ata)

    cartoes = (
        await session.scalars(
            select(CartaoSaude).where(CartaoSaude.user_id.in_(users_validos))
        )
    ).all()
    for cartao in cartoes:
        await session.delete(cartao)

    await session.commit()

    return success_response(
        data=OrfaosAeromedicaDeleteResponse(
            cartoes=len(cartoes),
            atas=len(atas),
        ),
        message=(
            f'{len(cartoes)} cartão(ões) e {len(atas)} ata(s) removido(s)'
        ),
    )


@router.get(
    '/{cartao_id}',
    response_model=ApiResponse[CartaoSaudeWithUser],
    dependencies=[ViewCartao],
)
async def get_cartao_saude_by_id(
    cartao_id: int,
    session: Session,
):
    """Busca cartao de saude por ID"""
    cartao = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.id == cartao_id)
    )

    if not cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao de saude nao encontrado',
        )

    return success_response(data=cartao)


@router.get(
    '/user/{user_id}',
    response_model=ApiResponse[CartaoSaudePublic | None],
)
async def get_cartao_saude_by_user(
    user_id: int,
    session: Session,
    user: CurrentUser,
    active_org: ActiveOrg,
):
    """Busca cartao de saude por ID do usuario.

    O próprio militar vê o seu cartão (self-service do FatBird) sem a
    permissão; terceiros exigem 'cartoes-saude.view' no vínculo da org
    ativa. Gate no handler (não como dependência) para permitir o owner.

    O gate autoriza a AÇÃO, não o ALVO: quem tem a permissão na sua unidade
    a teria sobre qualquer `user_id`. O escopo do alvo é a query — só cartões
    de militares da org ativa (`User.unidade`), como no resto do módulo.
    """
    await ensure_org_permission_or_owner(
        user, session, active_org, 'cartoes-saude', 'view', user_id
    )

    cartao = await session.scalar(
        select(CartaoSaude)
        .join(User, User.id == CartaoSaude.user_id)
        .where(
            CartaoSaude.user_id == user_id,
            User.unidade == active_org,
        )
    )

    return success_response(data=cartao)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[CartaoSaudePublic],
    dependencies=[CreateCartao],
)
async def create_cartao_saude(
    session: Session,
    active_org: ActiveOrg,
    dados: CartaoSaudeCreate,
):
    """Cria novo cartao de saude para um usuario"""
    user = await session.scalar(
        select(User).where(
            User.id == dados.user_id,
            User.unidade == active_org,
            User.active.is_(True),
        )
    )
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuario nao encontrado',
        )

    cartao_existente = await session.scalar(
        select(CartaoSaude).where(CartaoSaude.user_id == dados.user_id)
    )
    if cartao_existente:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=('Ja existe cartao de saude cadastrado para este usuario'),
        )

    dados_dict = dados.model_dump()
    new_cartao = CartaoSaude(**dados_dict)

    session.add(new_cartao)
    # Fecha a janela entre o check acima e o insert: duas requisições
    # concorrentes passam pelo check, mas o unique de user_id garante que
    # só uma persiste — a outra vira 400 em vez de 500.
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Ja existe cartao de saude cadastrado para este usuario',
        ) from exc
    await session.refresh(new_cartao)

    return success_response(
        data=CartaoSaudePublic.model_validate(new_cartao),
        message='Cartao de saude criado com sucesso',
    )


@router.put(
    '/{cartao_id}',
    response_model=ApiResponse[None],
    dependencies=[UpdateCartao],
)
async def update_cartao_saude(
    cartao_id: int,
    session: Session,
    active_org: ActiveOrg,
    dados: CartaoSaudeUpdate,
):
    """Atualiza cartao de saude existente"""
    db_cartao = await session.scalar(
        select(CartaoSaude)
        .join(User, User.id == CartaoSaude.user_id)
        .where(
            CartaoSaude.id == cartao_id,
            User.unidade == active_org,
            User.active.is_(True),
        )
    )

    if not db_cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao de saude nao encontrado',
        )

    for key, value in dados.model_dump(exclude_unset=True).items():
        setattr(db_cartao, key, value)

    await session.commit()
    await session.refresh(db_cartao)

    return success_response(message='Cartao de saude atualizado com sucesso')


@router.delete(
    '/{cartao_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteCartao],
)
async def delete_cartao_saude(
    cartao_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Deleta cartao de saude"""
    db_cartao = await session.scalar(
        select(CartaoSaude)
        .join(User, User.id == CartaoSaude.user_id)
        .where(
            CartaoSaude.id == cartao_id,
            User.unidade == active_org,
            User.active.is_(True),
        )
    )

    if not db_cartao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cartao de saude nao encontrado',
        )

    await session.delete(db_cartao)
    await session.commit()

    return success_response(message='Cartao de saude deletado com sucesso')
