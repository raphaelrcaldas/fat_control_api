from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sql_func
from sqlalchemy import select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import Etapa, OIEtapa, TripEtapa
from fcontrol_api.models.inteligencia.passaportes import Passaporte
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.models.seg_voo.crm import CrmCertificado
from fcontrol_api.schemas.estatistica.sebo import (
    SeboCartoes,
    SeboTripOut,
    SeboVoo,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/sebo', tags=['estatistica'])


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[SeboTripOut]],
)
async def list_sebo(
    session: Session,
    func: Annotated[str, Query()],
    oper: Annotated[list[str] | None, Query()] = None,
    func_bordo: Annotated[list[str] | None, Query()] = None,
    ano: Annotated[int | None, Query(ge=2020)] = None,
) -> ApiResponse[list[SeboTripOut]]:
    """Dados agregados do Pau de Sebo por tripulante."""
    ref_ano = ano or date.today().year
    jan1 = date(ref_ano, 1, 1)
    dec31 = date(ref_ano, 12, 31)

    sim_etapa_ids = (
        select(OIEtapa.etapa_id)
        .join(EsforcoAereo, EsforcoAereo.id == OIEtapa.esf_aer_id)
        .where(EsforcoAereo.descricao.contains('SML'))
        .scalar_subquery()
    )

    nao_sim = ~Etapa.id.in_(sim_etapa_ids)

    h_ano = sql_func.coalesce(
        sql_func.sum(Etapa.tvoo).filter(
            (Etapa.data >= jan1) & (Etapa.data <= dec31) & nao_sim
        ),
        0,
    ).label('h_ano')

    dsv = (
        sql_func.current_date()
        - sql_func.max(Etapa.data).filter((Etapa.data <= dec31) & nao_sim)
    ).label('dsv')

    data_ult_voo = (
        sql_func
        .max(Etapa.data)
        .filter((Etapa.data <= dec31) & nao_sim)
        .label('data_ult_voo')
    )

    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.p_g,
            User.nome_guerra,
            Tripulante.trig,
            Funcao.func,
            Funcao.oper,
            h_ano,
            dsv,
            data_ult_voo,
            CartaoSaude.cemal.label('cartao_cemal'),
            CartaoSaude.tovn.label('cartao_tovn'),
            CartaoSaude.imae.label('cartao_imae'),
            CrmCertificado.data_validade.label('cartao_crm'),
            Passaporte.validade_passaporte.label('cartao_val_pass'),
            Passaporte.validade_visa.label('cartao_val_visa'),
        )
        .select_from(Tripulante)
        .join(User, User.id == Tripulante.user_id)
        .outerjoin(
            CartaoSaude,
            CartaoSaude.user_id == User.id,
        )
        .outerjoin(
            CrmCertificado,
            CrmCertificado.user_id == User.id,
        )
        .outerjoin(
            Passaporte,
            Passaporte.user_id == User.id,
        )
        .join(
            Funcao,
            (Funcao.trip_id == Tripulante.id) & (Funcao.func == func),
        )
        .outerjoin(
            TripEtapa,
            (TripEtapa.trip_id == Tripulante.id)
            & (TripEtapa.func_bordo.in_(func_bordo) if func_bordo else true()),
        )
        .outerjoin(
            Etapa,
            Etapa.id == TripEtapa.etapa_id,
        )
        .where(Tripulante.active.is_(True))
        .group_by(
            Tripulante.id,
            User.p_g,
            User.nome_guerra,
            Tripulante.trig,
            Funcao.func,
            Funcao.oper,
            CartaoSaude.cemal,
            CartaoSaude.tovn,
            CartaoSaude.imae,
            CrmCertificado.data_validade,
            Passaporte.validade_passaporte,
            Passaporte.validade_visa,
        )
        .order_by(
            text('h_ano DESC'),
            Tripulante.id,
        )
    )

    if oper:
        query = query.where(Funcao.oper.in_(oper))

    rows = await session.execute(query)
    items = [
        SeboTripOut(
            trip_id=r.trip_id,
            p_g=r.p_g,
            nome_guerra=r.nome_guerra,
            trig=r.trig,
            func=r.func,
            oper=r.oper,
            voo=SeboVoo(
                h_ano=r.h_ano,
                dsv=r.dsv,
                data_ult_voo=r.data_ult_voo,
            ),
            cartoes=SeboCartoes(
                cemal=r.cartao_cemal,
                tovn=r.cartao_tovn,
                imae=r.cartao_imae,
                crm=r.cartao_crm,
                val_pass=r.cartao_val_pass,
                val_visa=r.cartao_val_visa,
            ),
        )
        for r in rows.all()
    ]

    return success_response(data=items)
