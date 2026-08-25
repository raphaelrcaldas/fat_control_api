from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.seg_voo.crm import CrmCertificado
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.seg_voo.crm import (
    CrmOrfaoPublic,
    CrmOrfaosDelete,
    CrmOrfaosDeleteResponse,
    CrmOrfaosResumo,
    CrmPublic,
    CrmUpdate,
    TripCrmOut,
)
from fcontrol_api.security import (
    ActiveOrg,
    ensure_org_permission_or_owner,
    get_current_user,
    permission_checker,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/crm', tags=['Seguranca de Voo'])

# CRM é qualificação da tripulação: leitura exige 'view' e cada escrita a
# sua ação. Admin da org ativa tem bypass (ver permission_checker). O
# self-service do FatBird (get por user) usa owner-OR-permission.
ViewCrm = Depends(permission_checker('seg_voo.crm', 'view'))
DeleteCrm = Depends(permission_checker('seg_voo.crm', 'delete'))


@router.get(
    '/',
    response_model=ApiResponse[list[TripCrmOut]],
    dependencies=[ViewCrm],
)
async def list_crm(
    session: Session,
    active_org: ActiveOrg,
    p_g: Annotated[str | None, Query()] = None,
    funcao: Annotated[str | None, Query()] = None,
):
    """Lista tripulantes ativos da org ativa com seus certificados CRM."""
    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.id.label('user_id'),
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            User.saram,
            User.telefone,
            Tripulante.trig,
            Tripulante.func,
            CrmCertificado.id.label('crm_id'),
            CrmCertificado.data_realizacao,
            CrmCertificado.data_validade,
        )
        .select_from(Tripulante)
        .join(User, User.id == Tripulante.user_id)
        .join(PostoGrad, PostoGrad.short == User.p_g)
        .outerjoin(
            CrmCertificado,
            CrmCertificado.user_id == User.id,
        )
        .where(
            Tripulante.active.is_(True),
            Tripulante.uae == active_org,
            User.active.is_(True),
        )
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
            User.id,
        )
    )

    if p_g:
        pgs = [p.strip() for p in p_g.split(',')]
        query = query.where(User.p_g.in_(pgs))

    if funcao:
        funcs = [f.strip() for f in funcao.split(',')]
        query = query.where(Tripulante.func.in_(funcs))

    rows = await session.execute(query)
    items = [
        TripCrmOut(
            trip_id=r.trip_id,
            user_id=r.user_id,
            p_g=r.p_g,
            nome_guerra=r.nome_guerra,
            nome_completo=r.nome_completo,
            saram=r.saram,
            telefone=r.telefone,
            trig=r.trig,
            func=r.func,
            crm=CrmPublic(
                id=r.crm_id,
                user_id=r.user_id,
                data_realizacao=r.data_realizacao,
                data_validade=r.data_validade,
            )
            if r.crm_id is not None
            else None,
        )
        for r in rows.all()
    ]

    return success_response(data=items)


@router.get('/user/{user_id}', response_model=ApiResponse[CrmPublic | None])
async def get_crm_by_user(
    user_id: int,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
):
    # O próprio militar vê o seu CRM (self-service do FatBird) sem a
    # permissão; terceiros exigem 'seg_voo.crm.view' no vínculo da org ativa.
    await ensure_org_permission_or_owner(
        user, session, active_org, 'seg_voo.crm', 'view', user_id
    )

    # Só retorna o CRM se o usuário for tripulante da org ativa.
    crm = await session.scalar(
        select(CrmCertificado)
        .join(Tripulante, Tripulante.user_id == CrmCertificado.user_id)
        .where(
            CrmCertificado.user_id == user_id,
            Tripulante.uae == active_org,
        )
    )
    return success_response(data=crm)


@router.get(
    '/orfaos',
    response_model=ApiResponse[CrmOrfaosResumo],
    dependencies=[ViewCrm],
)
async def get_crm_orfaos(session: Session, active_org: ActiveOrg):
    """Certificados CRM de militares inativos da org (limpeza)."""
    result = await session.execute(
        select(User)
        .join(CrmCertificado, CrmCertificado.user_id == User.id)
        .where(
            User.active.is_(False),
            User.unidade == active_org,
        )
        .order_by(User.nome_guerra, User.id)
    )

    itens = [
        CrmOrfaoPublic(
            user_id=militar.id,
            p_g=militar.p_g,
            nome_guerra=militar.nome_guerra,
            nome_completo=militar.nome_completo,
        )
        for militar in result.scalars().all()
    ]

    return success_response(
        data=CrmOrfaosResumo(total_registros=len(itens), itens=itens),
    )


@router.delete(
    '/orfaos',
    response_model=ApiResponse[CrmOrfaosDeleteResponse],
    dependencies=[DeleteCrm],
)
async def delete_crm_orfaos(
    payload: CrmOrfaosDelete,
    session: Session,
    active_org: ActiveOrg,
):
    """Remove os certificados CRM dos militares inativos selecionados."""
    users_validos = select(User.id).where(
        User.id.in_(payload.user_ids),
        User.active.is_(False),
        User.unidade == active_org,
    )

    crms = (
        await session.scalars(
            select(CrmCertificado).where(
                CrmCertificado.user_id.in_(users_validos)
            )
        )
    ).all()

    for crm in crms:
        await session.delete(crm)

    await session.commit()

    return success_response(
        data=CrmOrfaosDeleteResponse(deleted=len(crms)),
        message=f'{len(crms)} certificado(s) CRM removido(s)',
    )


@router.put(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def upsert_crm(
    trip_id: int,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
    dados: CrmUpdate,
):
    """Cria ou atualiza certificado CRM de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
            Tripulante.uae == active_org,
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    crm = await session.scalar(
        select(CrmCertificado).where(
            CrmCertificado.user_id == tripulante.user_id
        )
    )

    # Upsert exige a ação correspondente: 'update' se já existe, senão
    # 'create'. owner_id=None → cai direto na checagem de permissão.
    await ensure_org_permission_or_owner(
        user,
        session,
        active_org,
        'seg_voo.crm',
        'update' if crm else 'create',
        owner_id=None,
    )

    if crm:
        for key, value in dados.model_dump(exclude_unset=True).items():
            setattr(crm, key, value)
        message = 'Certificado CRM atualizado com sucesso'
    else:
        crm = CrmCertificado(
            user_id=tripulante.user_id,
            data_realizacao=dados.data_realizacao,
            data_validade=dados.data_validade,
        )
        session.add(crm)
        message = 'Certificado CRM cadastrado com sucesso'

    await session.commit()

    return success_response(message=message)


@router.delete(
    '/{trip_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteCrm],
)
async def delete_crm(
    trip_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Remove certificado CRM de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
            Tripulante.uae == active_org,
        )
    )
    if not tripulante:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    crm = await session.scalar(
        select(CrmCertificado).where(
            CrmCertificado.user_id == tripulante.user_id
        )
    )
    if not crm:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Certificado CRM nao encontrado',
        )

    await session.delete(crm)
    await session.commit()

    return success_response(message='Certificado CRM removido com sucesso')
