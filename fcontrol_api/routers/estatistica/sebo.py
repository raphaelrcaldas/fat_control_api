from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sql_func
from sqlalchemy import select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.estatistica.etapa import Etapa, Missao, TripEtapa
from fcontrol_api.models.instrucao.cartoes import Cartao
from fcontrol_api.models.inteligencia.passaportes import Passaporte
from fcontrol_api.models.seg_voo.crm import CrmCertificado
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.sebo import (
    SeboCartoes,
    SeboTripOut,
    SeboVoo,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg
from fcontrol_api.utils.params import parse_str_list
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
    active_org: ActiveOrg,
    func: Annotated[str, Query()],
    oper: Annotated[str | None, Query()] = None,
    func_bordo: Annotated[str | None, Query()] = None,
    ano: Annotated[int | None, Query(ge=2020)] = None,
) -> ApiResponse[list[SeboTripOut]]:
    """Dados agregados do Pau de Sebo por tripulante."""
    oper_list = parse_str_list(oper, 'oper')
    func_bordo_list = parse_str_list(func_bordo, 'func_bordo')
    ref_ano = ano or date.today().year
    jan1 = date(ref_ano, 1, 1)
    dec31 = date(ref_ano, 12, 31)

    # Ranking de horas voadas reais: simulador é o que a missão diz ser,
    # não a linha de esforço imputada — sessão sem OI também fica fora.
    nao_sim = Missao.is_simulador.is_(False)

    h_ano = sql_func.coalesce(
        sql_func.sum(Etapa.tvoo).filter(
            (Etapa.data >= jan1) & (Etapa.data <= dec31) & nao_sim
        ),
        0,
    ).label('h_ano')

    # DSV é estado atual, como a validade dos cartões: conta até hoje e
    # ignora o `ano`. Limitado a 31/12 do ano filtrado, um ano anterior
    # mostrava centenas de dias para quem voou ontem.
    hoje = sql_func.current_date()
    ult_voo = sql_func.max(Etapa.data).filter((Etapa.data <= hoje) & nao_sim)
    dsv = (hoje - ult_voo).label('dsv')
    data_ult_voo = ult_voo.label('data_ult_voo')

    query = (
        select(
            Tripulante.id.label('trip_id'),
            User.p_g,
            User.nome_guerra,
            Tripulante.trig,
            Tripulante.func,
            Tripulante.oper,
            h_ano,
            dsv,
            data_ult_voo,
            CartaoSaude.cemal.label('cartao_cemal'),
            CartaoSaude.tovn.label('cartao_tovn'),
            CartaoSaude.imae.label('cartao_imae'),
            CrmCertificado.data_validade.label('cartao_crm'),
            Passaporte.validade_passaporte.label('cartao_val_pass'),
            Passaporte.validade_visa.label('cartao_val_visa'),
            Cartao.cvi_validade.label('cartao_cvi'),
            Cartao.ptai_validade.label('cartao_ptai'),
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
        .outerjoin(
            Cartao,
            Cartao.user_id == User.id,
        )
        .outerjoin(
            TripEtapa,
            (TripEtapa.trip_id == Tripulante.id)
            & (
                TripEtapa.func_bordo.in_(func_bordo_list)
                if func_bordo_list
                else true()
            ),
        )
        .outerjoin(
            Etapa,
            Etapa.id == TripEtapa.etapa_id,
        )
        .outerjoin(
            Missao,
            Missao.id == Etapa.missao_id,
        )
        .where(
            Tripulante.active.is_(True),
            Tripulante.uae == active_org,
            Tripulante.func == func,
        )
        .group_by(
            Tripulante.id,
            User.p_g,
            User.nome_guerra,
            Tripulante.trig,
            Tripulante.func,
            Tripulante.oper,
            CartaoSaude.cemal,
            CartaoSaude.tovn,
            CartaoSaude.imae,
            CrmCertificado.data_validade,
            Passaporte.validade_passaporte,
            Passaporte.validade_visa,
            Cartao.cvi_validade,
            Cartao.ptai_validade,
        )
        .order_by(
            text('h_ano DESC'),
            Tripulante.id,
        )
    )

    if oper_list:
        query = query.where(Tripulante.oper.in_(oper_list))

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
                cvi=r.cartao_cvi,
                ptai=r.cartao_ptai,
            ),
        )
        for r in rows.all()
    ]

    return success_response(data=items)
