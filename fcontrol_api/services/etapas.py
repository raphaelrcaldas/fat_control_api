"""Funcoes de consulta de etapas, OIs e tripulantes."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, time

from sqlalchemy import and_, or_, select
from sqlalchemy import delete as sa_delete
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
from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.etapa import (
    HeavyCdsEtapaIn,
    HeavyCdsEtapaOut,
    OIEtapaIn,
    OIEtapaOut,
    PqdEtapaIn,
    PqdEtapaOut,
    RevoEtapaIn,
    RevoEtapaOut,
    TripEtapaIn,
    TripEtapaOut,
)


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


def compute_tvoo_minutes(dep: time, arr: time) -> int | None:
    """Tempo de voo (min) de dep->arr, ou None se atravessa o dia.

    Espelha a regra do banco (coluna Computed) e do validador do
    schema: arr deve ser > dep, com a excecao de arr == 00:00 tratado
    como fim do dia (1440).
    """
    start, end = _to_interval(dep, arr)
    if end <= start:
        return None
    return end - start


async def assert_no_trip_collision(
    session: AsyncSession,
    *,
    data: date,
    dep: time,
    arr: time,
    trip_ids: list[int],
    active_org: str,
    exclude_ids: list[int] | None = None,
) -> None:
    """Verifica se algum tripulante ja esta escalado em
    etapa com horario sobreposto na mesma data.

    Levanta ValueError descrevendo TODOS os tripulantes em
    conflito e suas etapas. Intervalos que apenas se tocam
    nao colidem. `exclude_ids` permite ignorar etapas (ex.:
    a propria etapa em edicao).

    A busca NAO filtra por organizacao, e isso e proposital: o
    militar e universal, estar em duas etapas simultaneas e conflito
    real venha de onde vier. O que muda e a FRASE — etapa de outra
    unidade e identificada so pela sigla da org, nunca por id,
    horario, matricula ou nome. Sem isso, variar data/anv e ler os
    422 mapeia a agenda de voo alheia. Ver
    `docs/ai/notes/rbac-e-isolamento.md`.
    """
    if not trip_ids:
        return

    new_start, new_end = _to_interval(dep, arr)

    stmt = (
        select(
            Etapa.id,
            Etapa.anv,
            Etapa.dep,
            Etapa.arr,
            TripEtapa.trip_id,
            Tripulante.trig,
            User.nome_guerra,
            Missao.uae,
        )
        .select_from(TripEtapa)
        .join(Etapa, Etapa.id == TripEtapa.etapa_id)
        .join(Missao, Missao.id == Etapa.missao_id)
        .join(Tripulante, Tripulante.id == TripEtapa.trip_id)
        .join(User, User.id == Tripulante.user_id)
        .where(
            Etapa.data == data,
            TripEtapa.trip_id.in_(trip_ids),
        )
    )
    if exclude_ids:
        stmt = stmt.where(~Etapa.id.in_(exclude_ids))

    rows = (await session.execute(stmt)).all()
    conflitos: list[str] = []
    for row in rows:
        ex_start, ex_end = _to_interval(row.dep, row.arr)
        if new_start < ex_end and ex_start < new_end:
            if row.uae == active_org:
                conflitos.append(
                    f'{row.trig} ({row.nome_guerra}) ja escalado '
                    f'na etapa #{row.id} ({row.anv}) '
                    f'{row.dep.strftime("%H:%M")}-'
                    f'{row.arr.strftime("%H:%M")}'
                )
            else:
                # Basta saber a quem recorrer; o resto e dado alheio.
                conflitos.append(
                    f'{row.trig} ({row.nome_guerra}) ja escalado '
                    f'em missao da {row.uae.upper()}'
                )

    if conflitos:
        msg = (
            f'Colisao de tripulantes em {data.isoformat()}: '
            + '; '.join(conflitos)
            + '.'
        )
        raise ValueError(msg)


async def assert_no_anv_collision(
    session: AsyncSession,
    *,
    data: date,
    anv: str,
    dep: time,
    arr: time,
    active_org: str,
    exclude_ids: list[int] | None = None,
) -> None:
    """Verifica se a aeronave ja tem etapa em horario sobreposto.

    Levanta ValueError com a etapa em conflito caso exista.
    Intervalos que apenas se tocam (ex.: 23:00->00:00 e
    00:00->01:00) nao colidem. `exclude_ids` permite ignorar
    etapas conhecidas (ex.: a propria etapa em edicao, ou
    etapas que serao removidas/atualizadas na mesma transacao).

    A busca NAO filtra por organizacao, e isso e proposital: uma
    cauda fisica nao voa em duas unidades ao mesmo tempo. O que muda
    e a FRASE — etapa de outra unidade e identificada so pela sigla
    da org. Ver `docs/ai/notes/rbac-e-isolamento.md`.
    """
    new_start, new_end = _to_interval(dep, arr)

    stmt = (
        select(Etapa, Missao.uae)
        .join(Missao, Missao.id == Etapa.missao_id)
        .where(
            Etapa.data == data,
            Etapa.anv == anv,
        )
    )
    if exclude_ids:
        stmt = stmt.where(~Etapa.id.in_(exclude_ids))

    rows = (await session.execute(stmt)).all()
    for existing, uae in rows:
        ex_start, ex_end = _to_interval(existing.dep, existing.arr)
        if new_start < ex_end and ex_start < new_end:
            if uae == active_org:
                msg = (
                    f'Colisao de horario para a aeronave {anv}: '
                    f'etapa #{existing.id} ja ocupa '
                    f'{existing.dep.strftime("%H:%M")}-'
                    f'{existing.arr.strftime("%H:%M")} '
                    f'em {data.isoformat()}.'
                )
            else:
                # Basta saber a quem recorrer; o resto e dado alheio.
                msg = (
                    f'Colisao de horario para a aeronave {anv} '
                    f'em {data.isoformat()}: ja em uso por missao '
                    f'da {uae.upper()}.'
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


def assert_no_internal_trip_collision(
    etapas: list[tuple[str, date, list[int], time, time]],
) -> None:
    """Verifica colisoes de tripulante entre etapas do mesmo payload.

    Cada tupla: (label, data, trip_ids, dep, arr). Duas etapas na
    mesma data com horarios sobrepostos e algum tripulante em comum
    colidem. Levanta ValueError descrevendo o par e os tripulantes
    em conflito.
    """
    intervals = [
        (label, d, set(trip_ids), *_to_interval(dep, arr))
        for label, d, trip_ids, dep, arr in etapas
    ]
    n = len(intervals)
    for i in range(n):
        la, da, ta, sa, ea = intervals[i]
        for j in range(i + 1, n):
            lb, db, tb, sb, eb = intervals[j]
            if da != db:
                continue
            if sa < eb and sb < ea:
                shared = ta & tb
                if shared:
                    ids = ', '.join(str(t) for t in sorted(shared))
                    msg = (
                        f'{la} e {lb}: tripulante(s) em conflito de '
                        f'horario em {da.isoformat()} (trip_id: {ids})'
                    )
                    raise ValueError(msg)


async def assert_anv_simulador_consistency(
    session: AsyncSession,
    *,
    pairs: Iterable[tuple[str, bool]],
) -> None:
    """Valida que o tipo da aeronave casa com o tipo da missao.

    `pairs` e uma colecao de (anv, is_simulador). Regras:
    - Missao de simulador (is_simulador=True) exige aeronave com
      `is_sim=True`.
    - Aeronave de simulador so pode ser usada em missao de
      simulador (impede usar o simulador em voo real e vice-versa).

    A consistencia se apoia em `Aeronave.is_sim` (fonte de verdade),
    nao numa matricula fixa. Levanta ValueError no primeiro conflito.
    """
    anvs = {anv.upper() for anv, _ in pairs}
    if not anvs:
        return

    rows = await session.execute(
        select(Aeronave.matricula, Aeronave.is_sim).where(
            Aeronave.matricula.in_(anvs)
        )
    )
    is_sim_by_anv = {matricula: is_sim for matricula, is_sim in rows.all()}

    for anv, is_simulador in pairs:
        key = anv.upper()
        anv_is_sim = is_sim_by_anv.get(key)
        if anv_is_sim is None:
            msg = f'Aeronave {key} nao encontrada'
            raise ValueError(msg)
        if is_simulador and not anv_is_sim:
            msg = (
                f'Missao de simulador exige aeronave de simulador; '
                f'{key} nao e simulador.'
            )
            raise ValueError(msg)
        if not is_simulador and anv_is_sim:
            msg = (
                f'Aeronave de simulador ({key}) so pode ser usada '
                f'em missao de simulador.'
            )
            raise ValueError(msg)


async def assert_tripulantes_da_org(
    session: AsyncSession,
    *,
    trip_ids: Iterable[int],
    uae: str,
) -> None:
    """Valida que todo `trip_id` do payload pertence a org ativa.

    O gate de permissao autoriza a ACAO, nao o ALVO, e o id do
    tripulante vem do corpo da requisicao. Sem este filtro, um id de
    outra unidade entra na etapa: a hora de voo e lancada no nome de
    militar alheio e o GET seguinte devolve trigrama, nome de guerra e
    posto dele — vazamento por enumeracao de id sequencial.

    Mesma regra ja aplicada no write-path da ordem de missao
    (`services/om.py::criar_tripulacao_batch`). A mensagem e neutra de
    proposito: nao revela que o id existe em outra organizacao.

    Uma unica query para todo o lote. Levanta ValueError, como as
    demais asserts deste modulo.
    """
    ids = {int(trip_id) for trip_id in trip_ids}
    if not ids:
        return

    validos = set(
        await session.scalars(
            select(Tripulante.id).where(
                Tripulante.id.in_(ids), Tripulante.uae == uae
            )
        )
    )
    faltando = sorted(ids - validos)
    if faltando:
        alvo = ', '.join(str(i) for i in faltando)
        msg = f'Tripulante(s) nao encontrado(s): {alvo}'
        raise ValueError(msg)


async def fetch_collision_candidates(
    session: AsyncSession,
    pairs: set[tuple[date, str]],
    *,
    exclude_ids: list[int] | None = None,
) -> dict[tuple[date, str], list[tuple[Etapa, str]]]:
    """Busca em lote etapas candidatas a colisao.

    Para cada (data, anv) em `pairs`, retorna (etapa, uae da missao)
    para todas as etapas no DB com aquela combinacao, excluindo
    `exclude_ids`. Resultado agrupado por (data, anv) para checagem
    O(1) por etapa do payload — substitui N round-trips por 1.

    A `uae` vem junto para o chamador decidir o que a mensagem de erro
    pode nomear: etapa de outra unidade nao pode ter id nem horario
    divulgados. Ver `docs/ai/notes/rbac-e-isolamento.md`.
    """
    if not pairs:
        return {}
    conditions = [and_(Etapa.data == d, Etapa.anv == a) for d, a in pairs]
    stmt = (
        select(Etapa, Missao.uae)
        .join(Missao, Missao.id == Etapa.missao_id)
        .where(or_(*conditions))
    )
    if exclude_ids:
        stmt = stmt.where(~Etapa.id.in_(exclude_ids))
    rows = (await session.execute(stmt)).all()
    result: dict[tuple[date, str], list[tuple[Etapa, str]]] = defaultdict(list)
    for c, uae in rows:
        result[(c.data, c.anv)].append((c, uae))
    return result


def find_collision(
    candidates: Iterable[tuple[Etapa, str]],
    *,
    dep: time,
    arr: time,
) -> tuple[Etapa, str] | None:
    """Retorna o primeiro (etapa, uae) em `candidates` que colide
    com o intervalo (dep, arr), ou None.

    Assume que todas as `candidates` ja foram filtradas por
    mesma data/anv. Intervalos que apenas se tocam nao colidem.
    """
    new_start, new_end = _to_interval(dep, arr)
    for ex, uae in candidates:
        ex_start, ex_end = _to_interval(ex.dep, ex.arr)
        if new_start < ex_end and ex_start < new_end:
            return ex, uae
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


async def limpar_filhos_de_etapas(
    session: AsyncSession, etapa_ids: Sequence[int]
) -> None:
    """Apaga em lote as linhas filhas das etapas informadas.

    Cobre as cinco tabelas dependentes de `etapas` (OIs, tripulantes,
    PQD, REVO e Heavy/CDS). Nao apaga a propria etapa: quem precisa
    remover a linha-mae faz o `DELETE` dela depois, e quem so esta
    reescrevendo os filhos (update em lote) chama apenas isto.

    Sem flush: o chamador controla o momento, mantendo a atomicidade
    da transacao.
    """
    if not etapa_ids:
        return
    ids = list(etapa_ids)
    for model in (OIEtapa, TripEtapa, PqdEtapa, REVOEtapa, HeavyCDS):
        await session.execute(sa_delete(model).where(model.etapa_id.in_(ids)))


def add_filhos_etapa(
    session: AsyncSession,
    etapa_id: int,
    *,
    tripulantes: Iterable[TripEtapaIn],
    oi_etapas: Iterable[OIEtapaIn],
    pqd: list[PqdEtapaIn],
    revo: list[RevoEtapaIn],
    heavy_cds: list[HeavyCdsEtapaIn],
) -> None:
    """Adiciona tripulantes, OIs e especificos de uma etapa.

    Criar uma etapa e reescrever uma etapa existente montam as mesmas
    linhas filhas; a unica diferenca e o `etapa_id`. Apenas faz
    `session.add` — flush/commit ficam com o chamador.
    """
    for t in tripulantes:
        session.add(
            TripEtapa(
                etapa_id=etapa_id,
                func=t.func,
                func_bordo=t.func_bordo,
                trip_id=t.trip_id,
            )
        )
    for oi in oi_etapas:
        session.add(
            OIEtapa(
                etapa_id=etapa_id,
                esf_aer_id=oi.esf_aer_id,
                tipo_missao_id=oi.tipo_missao_id,
                reg=oi.reg,
                tvoo=oi.tvoo,
            )
        )
    add_especificos(session, etapa_id, pqd=pqd, revo=revo, heavy_cds=heavy_cds)


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
