from calendar import monthrange
from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.relatorio_anual import (
    TripulanteRelatorio,
)
from fcontrol_api.schemas.estatistica.relatorio_mensal import RelatorioMensal
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    ensure_org_permission_or_owner,
    get_current_user,
)
from fcontrol_api.services.relatorio_mensal import apurar_mensal
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/tripulantes', tags=['estatistica'])
FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')


@router.get('/{trip_id}/relatorio-mensal')
async def get_relatorio_mensal(
    trip_id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
    ano: Annotated[int | None, Query(ge=2020, le=9999)] = None,
    mes: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> ApiResponse[RelatorioMensal]:
    """Etapas e acumulados até o mês, com acesso dono-ou-permissão."""
    trip = await session.scalar(
        select(Tripulante).where(
            Tripulante.id == trip_id,
            Tripulante.uae == active_org,
        )
    )
    if trip is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado',
        )
    await ensure_org_permission_or_owner(
        current_user,
        session,
        active_org,
        'ops.tripulantes',
        'view',
        trip.user_id,
    )
    hoje = datetime.now(FUSO_LOCAL).date()
    ref_ano = ano if ano is not None else hoje.year
    ref_mes = mes if mes is not None else hoje.month
    inicio = date(ref_ano, ref_mes, 1)
    fim = min(date(ref_ano, ref_mes, monthrange(ref_ano, ref_mes)[1]), hoje)
    aeronaves, simuladores = await apurar_mensal(
        session, trip.id, active_org, inicio, fim
    )
    return success_response(
        data=RelatorioMensal(
            ano=ref_ano,
            mes=ref_mes,
            tripulante=TripulanteRelatorio(
                id=trip.id,
                user_id=trip.user_id,
                trig=trip.trig,
                p_g=trip.user.posto.short,
                nome_guerra=trip.user.nome_guerra,
                nome_completo=trip.user.nome_completo,
            ),
            aeronaves=aeronaves,
            simuladores=simuladores,
        )
    )
