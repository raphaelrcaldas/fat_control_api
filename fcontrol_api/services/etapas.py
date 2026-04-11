"""Funcoes de consulta de etapas, OIs e tripulantes."""

from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
    TripEtapa,
)
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.estatistica.etapa import (
    EtapaFlatOut,
    OIEtapaOut,
    TripEtapaOut,
)
from fcontrol_api.schemas.response import ApiPaginatedResponse
from fcontrol_api.utils.responses import paginated_response


def like_safe(val: str) -> str:
    """Escapa caracteres especiais de LIKE."""
    return val.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


async def fetch_trip_data(
    session: AsyncSession,
    etapa_ids: list[int],
) -> dict[int, list[TripEtapaOut]]:
    """Busca tripulantes agrupados por etapa."""
    if not etapa_ids:
        return {}

    trip_data: dict[int, list[TripEtapaOut]] = {}
    trip_rows = await session.execute(
        select(
            TripEtapa.etapa_id,
            TripEtapa.trip_id,
            TripEtapa.func,
            TripEtapa.func_bordo,
            Tripulante.trig,
            User.nome_guerra,
            User.p_g,
            User.ult_promo,
            User.ant_rel,
            PostoGrad.ant,
        )
        .select_from(TripEtapa)
        .join(Tripulante, Tripulante.id == TripEtapa.trip_id)
        .join(User, User.id == Tripulante.user_id)
        .join(PostoGrad, PostoGrad.short == User.p_g)
        .where(TripEtapa.etapa_id.in_(etapa_ids))
        .order_by(TripEtapa.etapa_id, TripEtapa.id)
    )
    for row in trip_rows.all():
        trip_data.setdefault(row.etapa_id, []).append(
            TripEtapaOut(
                trip_id=row.trip_id,
                trig=row.trig,
                nome_guerra=row.nome_guerra,
                p_g=row.p_g,
                func=row.func,
                func_bordo=row.func_bordo,
                ant=row.ant,
                ult_promo=(
                    row.ult_promo.isoformat() if row.ult_promo else None
                ),
                ant_rel=row.ant_rel,
            )
        )

    return trip_data


async def fetch_oi_etapas(
    session: AsyncSession,
    etapa_id: int,
) -> list[OIEtapaOut]:
    """Busca OIEtapas estruturadas para o detail."""
    oi_rows = await session.execute(
        select(
            OIEtapa.esf_aer_id,
            OIEtapa.tipo_missao_id,
            EsforcoAereo.descricao.label('esf_descr'),
            TipoMissao.cod.label('tipo_cod'),
            OIEtapa.reg,
            OIEtapa.tvoo,
        )
        .select_from(OIEtapa)
        .join(
            EsforcoAereo,
            EsforcoAereo.id == OIEtapa.esf_aer_id,
        )
        .join(
            TipoMissao,
            TipoMissao.id == OIEtapa.tipo_missao_id,
        )
        .where(OIEtapa.etapa_id == etapa_id)
        .order_by(OIEtapa.id)
    )
    return [
        OIEtapaOut(
            esf_aer_id=row.esf_aer_id,
            tipo_missao_id=row.tipo_missao_id,
            esf_aer=row.esf_descr,
            tipo_missao_cod=row.tipo_cod,
            reg=row.reg,
            tvoo=row.tvoo,
        )
        for row in oi_rows.all()
    ]


async def fetch_oi_detail_data(
    session: AsyncSession,
    etapa_ids: list[int],
) -> dict[int, list[OIEtapaOut]]:
    """Busca OIEtapas completas agrupadas por etapa."""
    if not etapa_ids:
        return {}

    result: dict[int, list[OIEtapaOut]] = {}
    rows = await session.execute(
        select(
            OIEtapa.etapa_id,
            OIEtapa.esf_aer_id,
            OIEtapa.tipo_missao_id,
            EsforcoAereo.descricao.label('esf_descr'),
            TipoMissao.cod.label('tipo_cod'),
            OIEtapa.reg,
            OIEtapa.tvoo,
        )
        .select_from(OIEtapa)
        .join(
            EsforcoAereo,
            EsforcoAereo.id == OIEtapa.esf_aer_id,
        )
        .join(
            TipoMissao,
            TipoMissao.id == OIEtapa.tipo_missao_id,
        )
        .where(OIEtapa.etapa_id.in_(etapa_ids))
        .order_by(OIEtapa.etapa_id, OIEtapa.id)
    )
    for row in rows.all():
        result.setdefault(row.etapa_id, []).append(
            OIEtapaOut(
                esf_aer_id=row.esf_aer_id,
                tipo_missao_id=row.tipo_missao_id,
                esf_aer=row.esf_descr,
                tipo_missao_cod=row.tipo_cod,
                reg=row.reg,
                tvoo=row.tvoo,
            )
        )
    return result


async def list_etapas_flat(
    session: AsyncSession,
    valid_etapa_ids,
    page: int,
    per_page: int,
) -> ApiPaginatedResponse[EtapaFlatOut]:
    """Retorna etapas individuais paginadas (modo flat)."""
    valid_ids = select(valid_etapa_ids.c.id)

    total = (
        await session.scalar(
            select(sql_func.count()).select_from(valid_etapa_ids)
        )
    ) or 0

    offset = (page - 1) * per_page

    etapas_result = await session.scalars(
        select(Etapa)
        .where(Etapa.id.in_(valid_ids))
        .order_by(
            Etapa.data.desc(),
            Etapa.dep.desc(),
            Etapa.id.desc(),
        )
        .offset(offset)
        .limit(per_page)
    )
    etapas_page = etapas_result.all()

    if not etapas_page:
        return paginated_response(
            items=[],
            total=total,
            page=page,
            per_page=per_page,
        )

    page_etapa_ids = [e.id for e in etapas_page]

    oi_detail_data = await fetch_oi_detail_data(
        session,
        page_etapa_ids,
    )
    trip_data = await fetch_trip_data(session, page_etapa_ids)

    missao_ids = list({e.missao_id for e in etapas_page})
    missoes_result = await session.scalars(
        select(Missao).where(Missao.id.in_(missao_ids))
    )
    missoes = {m.id: m for m in missoes_result.all()}

    items = [
        EtapaFlatOut.model_validate(e).model_copy(
            update={
                'oi_etapas': oi_detail_data.get(
                    e.id,
                    [],
                ),
                'tripulantes': trip_data.get(e.id, []),
                'missao_id': e.missao_id,
                'missao_titulo': (
                    missoes[e.missao_id].titulo
                    if e.missao_id in missoes
                    else None
                ),
            }
        )
        for e in etapas_page
    ]

    return paginated_response(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )
