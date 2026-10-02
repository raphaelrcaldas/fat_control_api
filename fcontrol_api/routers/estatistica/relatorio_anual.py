from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TripEtapa,
)
from fcontrol_api.models.shared.aeronaves import Aeronave, ProjetoAnv
from fcontrol_api.models.shared.funcoes import Funcao, FuncaoUae
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.relatorio_anual import (
    RelatorioAnual,
    TripulanteRelatorio,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    ensure_org_permission_or_owner,
    get_current_user,
)
from fcontrol_api.services.relatorio_anual import EtapaApurada, apurar_resumo
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/tripulantes', tags=['estatistica'])

FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')


@router.get('/{trip_id}/relatorio-anual')
async def get_relatorio_anual(
    trip_id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
    ano: Annotated[int | None, Query(ge=2020, le=9999)] = None,
) -> ApiResponse[RelatorioAnual]:
    """Relatorio individual com acesso dono-ou-permissao na org ativa.

    Etapas com data posterior a hoje (dia local) ficam fora de tudo.
    """
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
    # Voo que ainda nao ocorreu nao compoe horas nem "ultimo voo".
    fim = min(date(ref_ano, 12, 31), hoje)
    # Agrega OIs ANTES de juntar a tripulacao: N OIs nao multiplicam a
    # duracao/pousos da etapa. Regime ausente permanece identificavel.
    regimes = (
        select(
            OIEtapa.etapa_id,
            sql_func
            .sum(OIEtapa.tvoo)
            .filter(OIEtapa.reg == 'd')
            .label('diurno'),
            sql_func
            .sum(OIEtapa.tvoo)
            .filter(OIEtapa.reg == 'n')
            .label('noturno'),
            sql_func.sum(OIEtapa.tvoo).filter(OIEtapa.reg == 'v').label('nvg'),
        )
        .join(Etapa, Etapa.id == OIEtapa.etapa_id)
        .join(Missao, Missao.id == Etapa.missao_id)
        .where(
            Missao.uae == active_org,
            Etapa.data >= date(ref_ano, 1, 1),
            Etapa.data <= fim,
            Etapa.id.in_(
                select(TripEtapa.etapa_id).where(TripEtapa.trip_id == trip.id)
            ),
        )
        .group_by(OIEtapa.etapa_id)
        .subquery()
    )
    rows = await session.execute(
        select(
            Etapa.id,
            Etapa.data,
            Etapa.tvoo,
            Etapa.pousos,
            Missao.is_simulador,
            TripEtapa.func,
            sql_func.coalesce(
                FuncaoUae.nome_custom, Funcao.nome, TripEtapa.func
            ).label('nome'),
            ProjetoAnv.modelo,
            sql_func.coalesce(regimes.c.diurno, 0).label('diurno'),
            sql_func.coalesce(regimes.c.noturno, 0).label('noturno'),
            sql_func.coalesce(regimes.c.nvg, 0).label('nvg'),
        )
        .select_from(TripEtapa)
        .join(Etapa, Etapa.id == TripEtapa.etapa_id)
        .join(Missao, Missao.id == Etapa.missao_id)
        .join(Aeronave, Aeronave.matricula == Etapa.anv)
        .join(ProjetoAnv, ProjetoAnv.id_projeto == Aeronave.projeto)
        .outerjoin(Funcao, Funcao.cod == TripEtapa.func)
        .outerjoin(
            FuncaoUae,
            (FuncaoUae.func_cod == TripEtapa.func)
            & (FuncaoUae.uae == active_org),
        )
        .outerjoin(regimes, regimes.c.etapa_id == Etapa.id)
        .where(
            TripEtapa.trip_id == trip.id,
            Missao.uae == active_org,
            Etapa.data >= date(ref_ano, 1, 1),
            Etapa.data <= fim,
        )
        .distinct()
        .order_by(Etapa.data, Etapa.id, TripEtapa.func)
    )
    etapas = [EtapaApurada(**r._mapping) for r in rows]
    return success_response(
        data=RelatorioAnual(
            ano=ref_ano,
            tripulante=TripulanteRelatorio(
                id=trip.id,
                user_id=trip.user_id,
                trig=trip.trig,
                p_g=trip.user.posto.short,
                nome_guerra=trip.user.nome_guerra,
                nome_completo=trip.user.nome_completo,
            ),
            aeronaves=apurar_resumo([e for e in etapas if not e.is_simulador]),
            simuladores=apurar_resumo([e for e in etapas if e.is_simulador]),
        )
    )
