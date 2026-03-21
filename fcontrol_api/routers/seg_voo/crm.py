from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.models.seg_voo.crm import CrmCertificado
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.seg_voo.crm import (
    CrmPublic,
    CrmUpdate,
    TripCrmOut,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/crm', tags=['Seguranca de Voo'])


@router.get(
    '/',
    response_model=ApiResponse[list[TripCrmOut]],
)
async def list_crm(
    session: Session,
    p_g: Annotated[str | None, Query()] = None,
    funcao: Annotated[str | None, Query()] = None,
):
    """Lista tripulantes ativos com seus certificados CRM."""
    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.id.label('user_id'),
            User.p_g,
            User.nome_guerra,
            User.nome_completo,
            User.saram,
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
        .where(Tripulante.active.is_(True))
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
        query = (
            query
            .join(Funcao, Funcao.trip_id == Tripulante.id)
            .where(Funcao.func.in_(funcs))
            .distinct()
        )

    rows = await session.execute(query)
    items = [
        TripCrmOut(
            trip_id=r.trip_id,
            user_id=r.user_id,
            p_g=r.p_g,
            nome_guerra=r.nome_guerra,
            nome_completo=r.nome_completo,
            saram=r.saram,
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


@router.put(
    '/{trip_id}',
    response_model=ApiResponse[None],
)
async def upsert_crm(
    trip_id: int,
    session: Session,
    dados: CrmUpdate,
):
    """Cria ou atualiza certificado CRM de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
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
)
async def delete_crm(
    trip_id: int,
    session: Session,
):
    """Remove certificado CRM de um tripulante."""
    tripulante = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.active.is_(True),
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
