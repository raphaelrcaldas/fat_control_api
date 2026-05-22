"""Funcoes de consulta de etapas, OIs e tripulantes."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, time

from sqlalchemy import and_, or_, select
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    HeavyCDS,
    Missao,
    OIEtapa,
    PqdEtapa,
    REVOEtapa,
    TipoMissao,
    TripEtapa,
)
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.etapa import (
    EtapaFlatOut,
    HeavyCdsEtapaIn,
    HeavyCdsEtapaOut,
    OIEtapaOut,
    PqdEtapaIn,
    PqdEtapaOut,
    RevoEtapaIn,
    RevoEtapaOut,
    TripEtapaOut,
)
from fcontrol_api.schemas.response import ApiPaginatedResponse
from fcontrol_api.utils.responses import paginated_response


def like_safe(val: str) -> str:
    """Escapa caracteres especiais de LIKE."""
    return val.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _to_interval(dep: time, arr: time) -> tuple[int, int]:
    """Converte dep/arr em intervalo [start, end] em minutos.

    arr == 00:00 com dep > 00:00 representa fim do dia (1440).
    """
    start = dep.hour * 60 + dep.minute
    end = arr.hour * 60 + arr.minute
    if end == 0 and start > 0:
        end = 1440
    return start, end


async def assert_no_anv_collision(
    session: AsyncSession,
    *,
    data: date,
    anv: str,
    dep: time,
    arr: time,
    exclude_ids: list[int] | None = None,
) -> None:
    """Verifica se a aeronave ja tem etapa em horario sobreposto.

    Levanta ValueError com a etapa em conflito caso exista.
    Intervalos que apenas se tocam (ex.: 23:00->00:00 e
    00:00->01:00) nao colidem. `exclude_ids` permite ignorar
    etapas conhecidas (ex.: a propria etapa em edicao, ou
    etapas que serao removidas/atualizadas na mesma transacao).
    """
    new_start, new_end = _to_interval(dep, arr)

    stmt = select(Etapa).where(
        Etapa.data == data,
        Etapa.anv == anv,
    )
    if exclude_ids:
        stmt = stmt.where(~Etapa.id.in_(exclude_ids))

    rows = await session.scalars(stmt)
    for existing in rows.all():
        ex_start, ex_end = _to_interval(existing.dep, existing.arr)
        if new_start < ex_end and ex_start < new_end:
            msg = (
                f'Colisao de horario para a aeronave {anv}: '
                f'etapa #{existing.id} ja ocupa '
                f'{existing.dep.strftime("%H:%M")}-'
                f'{existing.arr.strftime("%H:%M")} '
                f'em {data.isoformat()}.'
            )
            raise ValueError(msg)


def assert_no_internal_anv_collision(
    etapas: list[tuple[str, date, str, time, time]],
) -> None:
    """Verifica colisoes entre etapas do mesmo payload.

    Cada tupla: (label, data, anv, dep, arr). Levanta
    ValueError descrevendo o par em conflito.
    """
    intervals = [
        (label, d, anv, *_to_interval(dep, arr))
        for label, d, anv, dep, arr in etapas
    ]
    n = len(intervals)
    for i in range(n):
        la, da, anva, sa, ea = intervals[i]
        for j in range(i + 1, n):
            lb, db, anvb, sb, eb = intervals[j]
            if anva != anvb or da != db:
                continue
            if sa < eb and sb < ea:
                msg = (
                    f'{la} e {lb}: colisao de aeronave '
                    f'({anva}) em {da.isoformat()}'
                )
                raise ValueError(msg)


async def fetch_collision_candidates(
    session: AsyncSession,
    pairs: set[tuple[date, str]],
    *,
    exclude_ids: list[int] | None = None,
) -> dict[tuple[date, str], list[Etapa]]:
    """Busca em lote etapas candidatas a colisao.

    Para cada (data, anv) em `pairs`, retorna todas as etapas
    no DB com aquela combinacao, excluindo `exclude_ids`.
    Resultado agrupado por (data, anv) para checagem O(1)
    por etapa do payload — substitui N round-trips por 1.
    """
    if not pairs:
        return {}
    conditions = [and_(Etapa.data == d, Etapa.anv == a) for d, a in pairs]
    stmt = select(Etapa).where(or_(*conditions))
    if exclude_ids:
        stmt = stmt.where(~Etapa.id.in_(exclude_ids))
    rows = await session.scalars(stmt)
    result: dict[tuple[date, str], list[Etapa]] = defaultdict(list)
    for c in rows.all():
        result[(c.data, c.anv)].append(c)
    return result


def find_collision(
    candidates: Iterable[Etapa],
    *,
    dep: time,
    arr: time,
) -> Etapa | None:
    """Retorna a primeira etapa em `candidates` que colide com
    o intervalo (dep, arr), ou None.

    Assume que todas as `candidates` ja foram filtradas por
    mesma data/anv. Intervalos que apenas se tocam nao colidem.
    """
    new_start, new_end = _to_interval(dep, arr)
    for ex in candidates:
        ex_start, ex_end = _to_interval(ex.dep, ex.arr)
        if new_start < ex_end and ex_start < new_end:
            return ex
    return None


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
                ult_promo=row.ult_promo,
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


def add_especificos(
    session: AsyncSession,
    etapa_id: int,
    *,
    pqd: list[PqdEtapaIn],
    revo: list[RevoEtapaIn],
    heavy_cds: list[HeavyCdsEtapaIn],
) -> None:
    """Adiciona os especificos (PQD, REVO, Heavy/CDS) a sessao.

    Apenas faz `session.add` — o flush/commit fica a cargo do
    chamador, mantendo a atomicidade da transacao.
    """
    for p in pqd:
        session.add(PqdEtapa(etapa_id=etapa_id, tipo=p.tipo, qtd=p.qtd))
    for r in revo:
        session.add(REVOEtapa(etapa_id=etapa_id, comb_transf=r.comb_transf))
    for h in heavy_cds:
        session.add(
            HeavyCDS(
                etapa_id=etapa_id,
                tipo=h.tipo,
                peso=h.peso,
                dist=h.dist,
                radial=h.radial,
            )
        )


async def fetch_especificos_data(
    session: AsyncSession,
    etapa_ids: list[int],
) -> tuple[
    dict[int, list[PqdEtapaOut]],
    dict[int, list[RevoEtapaOut]],
    dict[int, list[HeavyCdsEtapaOut]],
]:
    """Busca especificos (PQD, REVO, Heavy/CDS) agrupados por etapa.

    Retorna uma tupla de tres dicts (pqd, revo, heavy_cds), cada um
    mapeando etapa_id -> lista de schemas Out. Etapas sem registros
    nao aparecem nos dicts.
    """
    pqd: dict[int, list[PqdEtapaOut]] = {}
    revo: dict[int, list[RevoEtapaOut]] = {}
    heavy_cds: dict[int, list[HeavyCdsEtapaOut]] = {}
    if not etapa_ids:
        return pqd, revo, heavy_cds

    pqd_rows = await session.scalars(
        select(PqdEtapa)
        .where(PqdEtapa.etapa_id.in_(etapa_ids))
        .order_by(PqdEtapa.etapa_id, PqdEtapa.id)
    )
    for row in pqd_rows.all():
        pqd.setdefault(row.etapa_id, []).append(
            PqdEtapaOut.model_validate(row)
        )

    revo_rows = await session.scalars(
        select(REVOEtapa)
        .where(REVOEtapa.etapa_id.in_(etapa_ids))
        .order_by(REVOEtapa.etapa_id, REVOEtapa.id)
    )
    for row in revo_rows.all():
        revo.setdefault(row.etapa_id, []).append(
            RevoEtapaOut.model_validate(row)
        )

    heavy_rows = await session.scalars(
        select(HeavyCDS)
        .where(HeavyCDS.etapa_id.in_(etapa_ids))
        .order_by(HeavyCDS.etapa_id, HeavyCDS.id)
    )
    for row in heavy_rows.all():
        heavy_cds.setdefault(row.etapa_id, []).append(
            HeavyCdsEtapaOut.model_validate(row)
        )

    return pqd, revo, heavy_cds


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
    pqd_data, revo_data, heavy_data = await fetch_especificos_data(
        session, page_etapa_ids
    )

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
                'pqd': pqd_data.get(e.id, []),
                'revo': revo_data.get(e.id, []),
                'heavy_cds': heavy_data.get(e.id, []),
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
