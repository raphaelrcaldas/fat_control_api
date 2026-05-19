from datetime import date, time
from http import HTTPStatus
from itertools import combinations
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TripEtapa,
)
from fcontrol_api.schemas.estatistica.etapa import (
    EtapaCreateNested,
    EtapaDetailOut,
    EtapaUpdateNested,
    MissaoComEtapasCreate,
    MissaoComEtapasDetailOut,
    MissaoComEtapasUpdate,
    MissaoCreate,
    MissaoPublic,
    MissaoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.services.etapas import (
    assert_no_anv_collision,
    assert_no_internal_anv_collision,
    fetch_collision_candidates,
    fetch_oi_detail_data,
    fetch_trip_data,
    find_collision,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
MissaoId = Annotated[int, Path()]

router = APIRouter(prefix='/missao', tags=['estatistica'])


@router.get(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoComEtapasDetailOut],
)
async def get_missao(
    missao_id: MissaoId,
    session: Session,
) -> ApiResponse[MissaoComEtapasDetailOut]:
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    etapas = list(
        await session.scalars(
            select(Etapa)
            .where(Etapa.missao_id == missao_id)
            .order_by(Etapa.data, Etapa.dep, Etapa.id)
        )
    )

    etapa_ids = [e.id for e in etapas]
    oi_detail_data = await fetch_oi_detail_data(session, etapa_ids)
    trip_data = await fetch_trip_data(session, etapa_ids)

    return success_response(
        data=MissaoComEtapasDetailOut(
            id=missao.id,
            titulo=missao.titulo,
            obs=missao.obs,
            is_simulador=missao.is_simulador,
            etapas=[
                EtapaDetailOut.model_validate(e).model_copy(
                    update={
                        'oi_etapas': oi_detail_data.get(e.id, []),
                        'tripulantes': trip_data.get(e.id, []),
                    }
                )
                for e in etapas
            ],
        ),
    )


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[MissaoPublic],
)
async def create_missao(
    missao: MissaoCreate,
    session: Session,
) -> ApiResponse[MissaoPublic]:
    new_missao = Missao(
        titulo=missao.titulo,
        obs=missao.obs,
        is_simulador=missao.is_simulador,
    )
    session.add(new_missao)
    await session.commit()
    await session.refresh(new_missao)

    return success_response(
        data=MissaoPublic.model_validate(new_missao),
        message='Missao criada com sucesso',
    )


@router.post(
    '/with-etapas',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[MissaoPublic],
)
async def create_missao_with_etapas(
    data: MissaoComEtapasCreate,
    session: Session,
) -> ApiResponse[MissaoPublic]:
    """Cria missao + etapas (com OIs e tripulantes) atomicamente.

    Em qualquer falha, o SQLAlchemy faz rollback total: nada
    persistido. tvoo eh Computed em SQL — nao enviamos no
    insert; o banco calcula via (arr - dep).
    """
    # Verificar colisao entre etapas do proprio payload
    for idx_a, idx_b in combinations(range(len(data.etapas)), 2):
        ea, eb = data.etapas[idx_a], data.etapas[idx_b]
        if ea.anv != eb.anv or ea.data != eb.data:
            continue
        start_a = ea.dep.hour * 60 + ea.dep.minute
        end_a = ea.arr.hour * 60 + ea.arr.minute
        if end_a == 0 and start_a > 0:
            end_a = 1440
        start_b = eb.dep.hour * 60 + eb.dep.minute
        end_b = eb.arr.hour * 60 + eb.arr.minute
        if end_b == 0 and start_b > 0:
            end_b = 1440
        if start_a < end_b and start_b < end_a:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=(
                    f'etapa[{idx_a}] e etapa[{idx_b}]: '
                    f'colisao de aeronave ({ea.anv}) '
                    f'em {ea.data.isoformat()}'
                ),
            )

    for idx, etapa_in in enumerate(data.etapas):
        try:
            await assert_no_anv_collision(
                session,
                data=etapa_in.data,
                anv=etapa_in.anv,
                dep=etapa_in.dep,
                arr=etapa_in.arr,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=f'etapa[{idx}]: {exc}',
            ) from exc

    new_missao = Missao(
        titulo=data.titulo,
        obs=data.obs,
        is_simulador=data.is_simulador,
    )
    session.add(new_missao)
    await session.flush()

    for etapa_in in data.etapas:
        etapa = Etapa(
            missao_id=new_missao.id,
            data=etapa_in.data,
            origem=etapa_in.origem.upper(),
            destino=etapa_in.destino.upper(),
            dep=etapa_in.dep,
            arr=etapa_in.arr,
            anv=etapa_in.anv.upper(),
            pousos=etapa_in.pousos,
            tow=etapa_in.tow,
            pax=etapa_in.pax,
            carga=etapa_in.carga,
            comb=etapa_in.comb,
            lub=etapa_in.lub,
            nivel=etapa_in.nivel,
            sagem=etapa_in.sagem,
            parte1=etapa_in.parte1,
            obs=etapa_in.obs,
        )
        session.add(etapa)
        await session.flush()

        for trip in etapa_in.tripulantes:
            session.add(
                TripEtapa(
                    etapa_id=etapa.id,
                    func=trip.func,
                    func_bordo=trip.func_bordo,
                    trip_id=trip.trip_id,
                )
            )

        for oi in etapa_in.oi_etapas:
            session.add(
                OIEtapa(
                    etapa_id=etapa.id,
                    esf_aer_id=oi.esf_aer_id,
                    tipo_missao_id=oi.tipo_missao_id,
                    reg=oi.reg,
                    tvoo=oi.tvoo,
                )
            )

    await session.commit()
    await session.refresh(new_missao)

    return success_response(
        data=MissaoPublic.model_validate(new_missao),
        message='Missao criada com sucesso',
    )


@router.put(
    '/{missao_id}/with-etapas',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoComEtapasDetailOut],
)
async def update_missao_with_etapas(
    missao_id: MissaoId,
    payload: MissaoComEtapasUpdate,
    session: Session,
) -> ApiResponse[MissaoComEtapasDetailOut]:
    """Atualiza missao + etapas atomicamente.

    Em qualquer falha (validacao, colisao, inexistencia) o
    SQLAlchemy faz rollback total da transacao. `is_simulador`
    e imutavel apos a criacao — nao e aceito no payload.
    """
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    # 1. Ownership: ids referenciados em delete_ids/update pertencem
    #    a esta missao. Pre-carregamos todas as etapas a atualizar
    #    em uma unica query, com filtro `missao_id` no proprio SELECT
    #    para evitar race com reparenting concorrente.
    update_ids = {e.id for e in payload.update}
    payload_ids = set(payload.delete_ids) | update_ids

    update_etapas_by_id: dict[int, Etapa] = {}
    if payload_ids:
        owned_rows = await session.scalars(
            select(Etapa.id).where(
                Etapa.missao_id == missao_id,
                Etapa.id.in_(payload_ids),
            )
        )
        db_ids = set(owned_rows.all())
        orphan = payload_ids - db_ids
        if orphan:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=(
                    f'Etapa(s) nao pertencem a missao '
                    f'#{missao_id}: {sorted(orphan)}'
                ),
            )
        if update_ids:
            update_rows = await session.scalars(
                select(Etapa).where(
                    Etapa.missao_id == missao_id,
                    Etapa.id.in_(update_ids),
                )
            )
            update_etapas_by_id = {e.id: e for e in update_rows.all()}

    # 2. Colisao interna ao payload (sync, sem DB).
    internal_etapas: list[tuple[str, date, str, time, time]] = [
        (f'create[{i}]', e.data, e.anv, e.dep, e.arr)
        for i, e in enumerate(payload.create)
    ] + [
        (f'update[{i}](id={e.id})', e.data, e.anv, e.dep, e.arr)
        for i, e in enumerate(payload.update)
    ]
    try:
        assert_no_internal_anv_collision(internal_etapas)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # 3. Colisao externa, em UMA query: pre-carrega todas as etapas
    #    no DB cuja (data, anv) bata com algum item do payload.
    exclude_ids = list(payload_ids)
    payload_etapas: list[tuple[str, EtapaUpdateNested | EtapaCreateNested]]
    payload_etapas = [
        (f'create[{i}]', e) for i, e in enumerate(payload.create)
    ] + [(f'update[{i}](id={e.id})', e) for i, e in enumerate(payload.update)]
    pairs = {(e.data, e.anv) for _, e in payload_etapas}
    candidates_by_key = await fetch_collision_candidates(
        session,
        pairs=pairs,
        exclude_ids=exclude_ids,
    )
    for label, e in payload_etapas:
        collision = find_collision(
            candidates_by_key.get((e.data, e.anv), []),
            dep=e.dep,
            arr=e.arr,
        )
        if collision is not None:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=(
                    f'{label}: colisao com etapa '
                    f'#{collision.id} '
                    f'({collision.dep.strftime("%H:%M")}-'
                    f'{collision.arr.strftime("%H:%M")}) '
                    f'em {e.data.isoformat()}.'
                ),
            )

    # 4. Patch direto (cliente sempre envia titulo/obs;
    #    semantica: PUT substitui, inclusive limpa pra None).
    missao.titulo = payload.titulo
    missao.obs = payload.obs

    # 5. Delete em lote (3 statements + flush).
    if payload.delete_ids:
        await session.execute(
            sa_delete(OIEtapa).where(OIEtapa.etapa_id.in_(payload.delete_ids))
        )
        await session.execute(
            sa_delete(TripEtapa).where(
                TripEtapa.etapa_id.in_(payload.delete_ids)
            )
        )
        await session.execute(
            sa_delete(Etapa).where(Etapa.id.in_(payload.delete_ids))
        )
        await session.flush()

    # 6. Update em lote: delete bulk de OIs/Trips das etapas
    #    atualizadas, depois patch dos campos e re-insercao.
    if payload.update:
        all_update_ids = list(update_ids)
        await session.execute(
            sa_delete(OIEtapa).where(OIEtapa.etapa_id.in_(all_update_ids))
        )
        await session.execute(
            sa_delete(TripEtapa).where(TripEtapa.etapa_id.in_(all_update_ids))
        )
        await session.flush()
        for e in payload.update:
            etapa = update_etapas_by_id[e.id]
            etapa.data = e.data
            etapa.origem = e.origem.upper()
            etapa.destino = e.destino.upper()
            etapa.dep = e.dep
            etapa.arr = e.arr
            etapa.anv = e.anv.upper()
            etapa.pousos = e.pousos
            etapa.tow = e.tow
            etapa.pax = e.pax
            etapa.carga = e.carga
            etapa.comb = e.comb
            etapa.lub = e.lub
            etapa.nivel = e.nivel
            etapa.sagem = e.sagem
            etapa.parte1 = e.parte1
            etapa.obs = e.obs
            for t in e.tripulantes:
                session.add(
                    TripEtapa(
                        etapa_id=e.id,
                        func=t.func,
                        func_bordo=t.func_bordo,
                        trip_id=t.trip_id,
                    )
                )
            for oi in e.oi_etapas:
                session.add(
                    OIEtapa(
                        etapa_id=e.id,
                        esf_aer_id=oi.esf_aer_id,
                        tipo_missao_id=oi.tipo_missao_id,
                        reg=oi.reg,
                        tvoo=oi.tvoo,
                    )
                )

    # 7. Create de novas etapas + suas OIs/Trips.
    for e in payload.create:
        new_etapa = Etapa(
            missao_id=missao_id,
            data=e.data,
            origem=e.origem.upper(),
            destino=e.destino.upper(),
            dep=e.dep,
            arr=e.arr,
            anv=e.anv.upper(),
            pousos=e.pousos,
            tow=e.tow,
            pax=e.pax,
            carga=e.carga,
            comb=e.comb,
            lub=e.lub,
            nivel=e.nivel,
            sagem=e.sagem,
            parte1=e.parte1,
            obs=e.obs,
        )
        session.add(new_etapa)
        await session.flush()
        for t in e.tripulantes:
            session.add(
                TripEtapa(
                    etapa_id=new_etapa.id,
                    func=t.func,
                    func_bordo=t.func_bordo,
                    trip_id=t.trip_id,
                )
            )
        for oi in e.oi_etapas:
            session.add(
                OIEtapa(
                    etapa_id=new_etapa.id,
                    esf_aer_id=oi.esf_aer_id,
                    tipo_missao_id=oi.tipo_missao_id,
                    reg=oi.reg,
                    tvoo=oi.tvoo,
                )
            )

    # 8. Capturar campos da missao em locais ANTES do commit
    #    para evitar lazy-load (expire_on_commit default).
    resp_id = missao.id
    resp_titulo = missao.titulo
    resp_obs = missao.obs
    resp_is_sim = missao.is_simulador

    await session.commit()

    # 9. Buscar estado final hidratado.
    etapas_rows = await session.scalars(
        select(Etapa)
        .where(Etapa.missao_id == missao_id)
        .order_by(Etapa.data, Etapa.dep, Etapa.id)
    )
    etapas = list(etapas_rows)
    etapa_ids = [e.id for e in etapas]
    oi_data = await fetch_oi_detail_data(session, etapa_ids)
    trip_data = await fetch_trip_data(session, etapa_ids)

    return success_response(
        data=MissaoComEtapasDetailOut(
            id=resp_id,
            titulo=resp_titulo,
            obs=resp_obs,
            is_simulador=resp_is_sim,
            etapas=[
                EtapaDetailOut.model_validate(e).model_copy(
                    update={
                        'oi_etapas': oi_data.get(e.id, []),
                        'tripulantes': trip_data.get(e.id, []),
                    }
                )
                for e in etapas
            ],
        ),
        message='Missao atualizada com sucesso',
    )


@router.put(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoPublic],
)
async def update_missao(
    missao_id: MissaoId,
    missao_data: MissaoUpdate,
    session: Session,
) -> ApiResponse[MissaoPublic]:
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    if missao_data.titulo is not None:
        missao.titulo = missao_data.titulo
    if missao_data.obs is not None:
        missao.obs = missao_data.obs

    await session.commit()
    await session.refresh(missao)

    return success_response(
        data=MissaoPublic.model_validate(missao),
        message='Missao atualizada com sucesso',
    )


@router.delete(
    '/{missao_id}/com-etapas',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_missao_com_etapas(
    missao_id: MissaoId,
    session: Session,
) -> ApiResponse[None]:
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    etapa_ids = list(
        await session.scalars(
            select(Etapa.id).where(Etapa.missao_id == missao_id)
        )
    )

    if etapa_ids:
        await session.execute(
            sa_delete(OIEtapa).where(OIEtapa.etapa_id.in_(etapa_ids))
        )
        await session.execute(
            sa_delete(TripEtapa).where(TripEtapa.etapa_id.in_(etapa_ids))
        )
        await session.execute(sa_delete(Etapa).where(Etapa.id.in_(etapa_ids)))

    await session.delete(missao)
    await session.commit()

    return success_response(
        message='Missao e etapas excluidas com sucesso',
    )


@router.delete(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_missao(
    missao_id: MissaoId,
    session: Session,
) -> ApiResponse[None]:
    missao = await session.scalar(select(Missao).where(Missao.id == missao_id))
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missao nao encontrada',
        )

    has_etapas = await session.scalar(
        select(Etapa.id).where(Etapa.missao_id == missao_id).limit(1)
    )
    if has_etapas:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Nao e possivel excluir missao com etapas vinculadas',
        )

    await session.delete(missao)
    await session.commit()

    return success_response(
        message='Missao excluida com sucesso',
    )
