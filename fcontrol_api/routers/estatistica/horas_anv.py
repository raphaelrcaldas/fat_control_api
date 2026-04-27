from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.esf_aer import (
    EsforcoAereo,
)
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    OIEtapa,
)
from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.schemas.estatistica.horas_anv import (
    AnvHorasResponse,
    AnvHorasRow,
    AnvMesData,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
AnoRef = Annotated[int, Query(ge=2020)]

router = APIRouter(prefix='/horas-anv', tags=['estatistica'])


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[AnvHorasResponse],
)
async def get_horas_anv(
    session: Session,
    ano_ref: AnoRef,
):
    # ANVs com voo nao-GTT no ano
    not_gtt_anvs = (
        select(Etapa.anv)
        .join(
            OIEtapa,
            OIEtapa.etapa_id == Etapa.id,
        )
        .join(
            EsforcoAereo,
            EsforcoAereo.id == OIEtapa.esf_aer_id,
        )
        .where(
            extract('year', Etapa.data) == ano_ref,
            ~EsforcoAereo.descricao.contains('GTT'),
        )
        .distinct()
        .scalar_subquery()
    )

    # Filtro: nao simulador E (ativa OU sem GTT)
    valid_filter = [
        Aeronave.is_sim.is_(False),
        or_(
            Aeronave.active.is_(True),
            Aeronave.matricula.in_(not_gtt_anvs),
        ),
    ]

    anvs_result = await session.execute(
        select(Aeronave.matricula)
        .where(*valid_filter)
        .order_by(Aeronave.matricula)
    )
    valid_anvs = [r[0] for r in anvs_result.all()]

    if not valid_anvs:
        return success_response(
            data=AnvHorasResponse(
                items=[],
                total_meses=[AnvMesData(tvoo=0, pousos=0) for _ in range(12)],
                total_tvoo=0,
                total_pousos=0,
            )
        )

    # Agregar etapas por ANV e mes
    mes_col = extract('month', Etapa.data).label('mes')

    agg = await session.execute(
        select(
            Etapa.anv,
            mes_col,
            func.coalesce(func.sum(Etapa.tvoo), 0).label('tvoo'),
            func.coalesce(func.sum(Etapa.pousos), 0).label('pousos'),
        )
        .where(
            extract('year', Etapa.data) == ano_ref,
            Etapa.anv.in_(valid_anvs),
        )
        .group_by(Etapa.anv, mes_col)
    )

    lookup: dict[tuple[str, int], tuple[int, int]] = {
        (r.anv, int(r.mes)): (r.tvoo, r.pousos) for r in agg.all()
    }

    # Montar resposta
    items: list[AnvHorasRow] = []
    t_tvoo = [0] * 12
    t_pousos = [0] * 12
    g_tvoo = 0
    g_pousos = 0

    for anv in valid_anvs:
        meses = []
        r_tvoo = 0
        r_pousos = 0
        for m in range(1, 13):
            tv, po = lookup.get((anv, m), (0, 0))
            meses.append(AnvMesData(tvoo=tv, pousos=po))
            r_tvoo += tv
            r_pousos += po
            t_tvoo[m - 1] += tv
            t_pousos[m - 1] += po

        items.append(
            AnvHorasRow(
                matricula=anv,
                meses=meses,
                total_tvoo=r_tvoo,
                total_pousos=r_pousos,
            )
        )
        g_tvoo += r_tvoo
        g_pousos += r_pousos

    total_meses = [
        AnvMesData(
            tvoo=t_tvoo[i],
            pousos=t_pousos[i],
        )
        for i in range(12)
    ]

    return success_response(
        data=AnvHorasResponse(
            items=items,
            total_meses=total_meses,
            total_tvoo=g_tvoo,
            total_pousos=g_pousos,
        )
    )
