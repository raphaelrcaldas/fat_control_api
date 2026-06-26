from collections import defaultdict
from datetime import date
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import Etapa, OIEtapa, TripEtapa
from fcontrol_api.models.shared.funcoes import Funcao
from fcontrol_api.models.shared.indisp import Indisp
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.quads import Quad, QuadsGroup, QuadsType
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.funcoes import funcs, proj
from fcontrol_api.schemas.ops.escala import (
    EscalaFuncSection,
    EscalaIndispInfo,
    EscalaResponse,
    EscalaTripEntry,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/escala', tags=['ops'])

ESCALA_ELIGIBLE_GROUPS = ('sobr', 'nasc', 'local', 'inter')


@router.get(
    '/disponiveis',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[EscalaResponse],
)
async def get_escala_disponiveis(
    session: Session,
    date_start: Annotated[date, Query()],
    date_end: Annotated[date, Query()],
    tipo_quad_id: Annotated[int, Query()],
    funcs_param: Annotated[list[funcs], Query(alias='funcs', min_length=1)],
    sort: Annotated[Literal['horas_voo', 'quads_asc'], Query()],
    active_org: ActiveOrg,
    proj_param: Annotated[proj, Query(alias='proj')] = 'kc-390',
):
    """Tripulantes disponíveis para escala em uma janela de datas."""
    if date_end < date_start:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='date_end deve ser maior ou igual a date_start',
        )

    # 1. Validar que tipo_quad_id pertence a grupo elegível
    eligible_check = await session.scalar(
        select(QuadsType.id)
        .join(QuadsGroup, QuadsGroup.id == QuadsType.group_id)
        .where(
            QuadsType.id == tipo_quad_id,
            QuadsGroup.short.in_(ESCALA_ELIGIBLE_GROUPS),
        )
    )
    if eligible_check is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Tipo de quadrinho fora dos grupos elegíveis para escala',
        )

    # 2. Subquery data_ult_voo (excluindo simulador SML)
    sim_etapa_ids = (
        select(OIEtapa.etapa_id)
        .join(EsforcoAereo, EsforcoAereo.id == OIEtapa.esf_aer_id)
        .where(EsforcoAereo.descricao.contains('SML'))
        .scalar_subquery()
    )
    nao_sim = ~Etapa.id.in_(sim_etapa_ids)
    data_ult_voo_subq = (
        select(
            TripEtapa.trip_id.label('trip_id'),
            sql_func.max(Etapa.data).label('data_ult_voo'),
        )
        .join(Etapa, Etapa.id == TripEtapa.etapa_id)
        .where(nao_sim)
        .group_by(TripEtapa.trip_id)
        .subquery()
    )

    # 3. Subquery quads_count para o tipo solicitado
    quads_count_subq = (
        select(
            Quad.trip_id.label('trip_id'),
            sql_func.count(Quad.id).label('total_quads'),
        )
        .where(Quad.type_id == tipo_quad_id)
        .group_by(Quad.trip_id)
        .subquery()
    )

    total_quads_expr = sql_func.coalesce(
        quads_count_subq.c.total_quads, 0
    ).label('total_quads')

    # 3b. Subquery tvoo_year: minutos voados no ano de date_end (sem SML)
    ano_ref = date_end.year
    tvoo_year_subq = (
        select(
            TripEtapa.trip_id.label('trip_id'),
            sql_func.coalesce(sql_func.sum(Etapa.tvoo), 0).label('tvoo_year'),
        )
        .join(Etapa, Etapa.id == TripEtapa.etapa_id)
        .where(nao_sim, extract('year', Etapa.data) == ano_ref)
        .group_by(TripEtapa.trip_id)
        .subquery()
    )

    tvoo_year_expr = sql_func.coalesce(tvoo_year_subq.c.tvoo_year, 0).label(
        'tvoo_year'
    )

    # 4. Query principal: tripulantes elegíveis
    trips_query = (
        select(
            Tripulante.id.label('trip_id'),
            Tripulante.trig,
            Tripulante.user_id,
            User.nome_guerra,
            User.p_g,
            Funcao.func,
            Funcao.oper,
            total_quads_expr,
            tvoo_year_expr,
            data_ult_voo_subq.c.data_ult_voo,
            CartaoSaude.cemal,
        )
        .select_from(Tripulante)
        .join(User, User.id == Tripulante.user_id)
        .join(PostoGrad, PostoGrad.short == User.p_g)
        .join(
            Funcao,
            (Funcao.trip_id == Tripulante.id)
            & (Funcao.func.in_(funcs_param))
            & (Funcao.oper != 'al')
            & (Funcao.proj == proj_param)
            & (Funcao.data_op.is_not(None)),
        )
        .outerjoin(CartaoSaude, CartaoSaude.user_id == User.id)
        .outerjoin(
            data_ult_voo_subq,
            data_ult_voo_subq.c.trip_id == Tripulante.id,
        )
        .outerjoin(
            quads_count_subq,
            quads_count_subq.c.trip_id == Tripulante.id,
        )
        .outerjoin(
            tvoo_year_subq,
            tvoo_year_subq.c.trip_id == Tripulante.id,
        )
        .where(
            Tripulante.uae == active_org,
            Tripulante.active.is_(True),
        )
    )

    if sort == 'horas_voo':
        trips_query = trips_query.order_by(
            tvoo_year_expr.asc(),
            PostoGrad.ant.asc(),
            Tripulante.id.asc(),
        )
    else:
        trips_query = trips_query.order_by(
            total_quads_expr.asc(),
            PostoGrad.ant.asc(),
            Tripulante.id.asc(),
        )

    trips_result = await session.execute(trips_query)
    rows = trips_result.all()

    # 5. Batch de indisponibilidades com overlap na janela
    user_ids = list({row.user_id for row in rows})
    indisps_by_user: defaultdict[int, list[EscalaIndispInfo]] = defaultdict(
        list
    )

    if user_ids:
        indisp_query = select(Indisp).where(
            Indisp.user_id.in_(user_ids),
            Indisp.deleted_at.is_(None),
            Indisp.date_end >= date_start,
            Indisp.date_start <= date_end,
        )
        indisps_result = await session.scalars(indisp_query)
        for indisp in indisps_result:
            indisps_by_user[indisp.user_id].append(
                EscalaIndispInfo.model_validate(indisp)
            )

    # 6. Agrupar por função (preservando ordem da query)
    sections_map: dict[str, list[EscalaTripEntry]] = {
        f: [] for f in funcs_param
    }
    for row in rows:
        if row.func not in sections_map:
            continue
        sections_map[row.func].append(
            EscalaTripEntry(
                id=row.trip_id,
                user_id=row.user_id,
                nome_guerra=row.nome_guerra,
                p_g=row.p_g,
                trig=row.trig,
                func=row.func,
                oper=row.oper,
                quads_count=int(row.total_quads or 0),
                tvoo_year=int(row.tvoo_year or 0),
                data_ult_voo=row.data_ult_voo,
                cemal_date=row.cemal,
                indisps=indisps_by_user.get(row.user_id, []),
            )
        )

    sections = [
        EscalaFuncSection(func=f, trips=sections_map[f]) for f in funcs_param
    ]

    response = EscalaResponse(
        date_start=date_start,
        date_end=date_end,
        sort=sort,
        tipo_quad_id=tipo_quad_id,
        sections=sections,
    )

    return success_response(data=response)
