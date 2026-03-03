from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.esf_aer import (
    EsfAerAloc,
    EsforcoAereo,
)
from fcontrol_api.models.estatistica.etapa import Etapa, OIEtapa
from fcontrol_api.schemas.estatistica.esf_aer import (
    EsfAerItem,
    EsfAerResumoItem,
    EsfAerResumoResponse,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
AnoRef = Annotated[int, Query(ge=2020)]

router = APIRouter(prefix='/esfaer', tags=['estatistica'])


@router.get(
    '/list',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[EsfAerItem]],
)
async def list_esf_aer_items(session: Session):
    """Lista todos os itens de Esforco Aereo para selects de formulario."""
    result = await session.execute(
        select(
            EsforcoAereo.id,
            EsforcoAereo.descricao,
        ).order_by(EsforcoAereo.descricao)
    )
    rows = result.all()
    return success_response(
        data=[EsfAerItem(id=row.id, descricao=row.descricao) for row in rows]
    )


def _mes_col(mes: int):
    """Gera coluna SUM condicional para um mês."""
    return func.coalesce(
        func.sum(
            case(
                (extract('month', Etapa.data) == mes, OIEtapa.tvoo),
                else_=0,
            )
        ),
        0,
    ).label(f'm{mes}')


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[EsfAerResumoResponse],
)
async def get_esf_aer_resumo(
    session: Session,
    ano_ref: AnoRef,
):
    meses_cols = [_mes_col(m) for m in range(1, 13)]

    query = (
        select(
            EsforcoAereo.id,
            EsforcoAereo.descricao,
            func.coalesce(EsfAerAloc.alocado, 0).label('alocado'),
            func.coalesce(
                func.sum(
                    case(
                        (Etapa.id.isnot(None), OIEtapa.tvoo),
                        else_=0,
                    )
                ),
                0,
            ).label('voado'),
            *meses_cols,
        )
        .outerjoin(
            EsfAerAloc,
            (EsfAerAloc.esfaer_id == EsforcoAereo.id)
            & (EsfAerAloc.ano_ref == ano_ref),
        )
        .outerjoin(
            OIEtapa,
            OIEtapa.esf_aer_id == EsforcoAereo.id,
        )
        .outerjoin(
            Etapa,
            (Etapa.id == OIEtapa.etapa_id)
            & (extract('year', Etapa.data) == ano_ref),
        )
        .group_by(
            EsforcoAereo.id,
            EsforcoAereo.descricao,
            EsfAerAloc.alocado,
        )
        .having(
            or_(
                func.coalesce(EsfAerAloc.alocado, 0) > 0,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Etapa.id.isnot(None),
                                OIEtapa.tvoo,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                )
                > 0,
            )
        )
        .order_by(EsforcoAereo.descricao)
    )

    result = await session.execute(query)
    rows = result.all()

    items = []
    total_alocado = 0
    total_voado = 0
    total_meses = [0] * 12

    for row in rows:
        alocado = row.alocado
        voado = row.voado
        meses = [getattr(row, f'm{m}') for m in range(1, 13)]

        items.append(
            EsfAerResumoItem(
                id=row.id,
                descricao=row.descricao,
                alocado=alocado,
                voado=voado,
                saldo=alocado - voado,
                meses=meses,
            )
        )

        total_alocado += alocado
        total_voado += voado
        for i in range(12):
            total_meses[i] += meses[i]

    return success_response(
        data=EsfAerResumoResponse(
            items=items,
            total_alocado=total_alocado,
            total_voado=total_voado,
            total_saldo=total_alocado - total_voado,
            total_meses=total_meses,
        )
    )
