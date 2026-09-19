from datetime import date, time
from http import HTTPStatus
from itertools import combinations
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import Etapa, Missao
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
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.services.etapas import (
    add_filhos_etapa,
    assert_anv_simulador_consistency,
    assert_no_anv_collision,
    assert_no_internal_anv_collision,
    assert_no_internal_trip_collision,
    assert_no_trip_collision,
    assert_tripulantes_da_org,
    fetch_collision_candidates,
    fetch_especificos_data,
    fetch_oi_detail_data,
    fetch_trip_data,
    find_collision,
    limpar_filhos_de_etapas,
)
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
MissaoId = Annotated[int, Path()]

router = APIRouter(prefix='/missao', tags=['estatistica'])

# Missão de estatística é o agrupador das etapas e divide o mesmo
# recurso: quem lança etapa lança a missão que as carrega.
ViewMissaoEtp = Depends(permission_checker('estatistica.etapas', 'view'))
CreateMissaoEtp = Depends(permission_checker('estatistica.etapas', 'create'))
UpdateMissaoEtp = Depends(permission_checker('estatistica.etapas', 'update'))
DeleteMissaoEtp = Depends(permission_checker('estatistica.etapas', 'delete'))


@router.get(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoComEtapasDetailOut],
    dependencies=[ViewMissaoEtp],
)
async def get_missao(
    missao_id: MissaoId,
    session: Session,
    active_org: ActiveOrg,
) -> ApiResponse[MissaoComEtapasDetailOut]:
    missao = await session.scalar(
        select(Missao).where(Missao.id == missao_id, Missao.uae == active_org)
    )
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada',
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
    pqd_data, revo_data, heavy_data = await fetch_especificos_data(
        session, etapa_ids
    )

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
                        'pqd': pqd_data.get(e.id, []),
                        'revo': revo_data.get(e.id, []),
                        'heavy_cds': heavy_data.get(e.id, []),
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
    dependencies=[CreateMissaoEtp],
)
async def create_missao(
    missao: MissaoCreate,
    session: Session,
    active_org: ActiveOrg,
) -> ApiResponse[MissaoPublic]:
    new_missao = Missao(
        titulo=missao.titulo,
        obs=missao.obs,
        uae=active_org,
        is_simulador=missao.is_simulador,
    )
    session.add(new_missao)
    await session.commit()
    await session.refresh(new_missao)

    return success_response(
        data=MissaoPublic.model_validate(new_missao),
        message='Missão criada com sucesso',
    )


@router.post(
    '/with-etapas',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[MissaoPublic],
    dependencies=[CreateMissaoEtp],
)
async def create_missao_with_etapas(
    data: MissaoComEtapasCreate,
    session: Session,
    active_org: ActiveOrg,
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

    # Colisao de tripulante entre etapas do proprio payload.
    try:
        assert_no_internal_trip_collision([
            (
                f'etapa[{i}]',
                e.data,
                [t.trip_id for t in e.tripulantes],
                e.dep,
                e.arr,
            )
            for i, e in enumerate(data.etapas)
        ])
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Escopo do ALVO: o gate autoriza a acao, nao o tripulante cujo id
    # veio no corpo. Em lote, antes do laco — uma query para todas as
    # etapas do payload.
    try:
        await assert_tripulantes_da_org(
            session,
            trip_ids=[t.trip_id for e in data.etapas for t in e.tripulantes],
            uae=active_org,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    for idx, etapa_in in enumerate(data.etapas):
        try:
            await assert_anv_simulador_consistency(
                session,
                pairs=[(etapa_in.anv, data.is_simulador)],
            )
            await assert_no_anv_collision(
                session,
                data=etapa_in.data,
                anv=etapa_in.anv,
                dep=etapa_in.dep,
                arr=etapa_in.arr,
                active_org=active_org,
            )
            await assert_no_trip_collision(
                session,
                data=etapa_in.data,
                dep=etapa_in.dep,
                arr=etapa_in.arr,
                trip_ids=[t.trip_id for t in etapa_in.tripulantes],
                active_org=active_org,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=f'etapa[{idx}]: {exc}',
            ) from exc

    new_missao = Missao(
        titulo=data.titulo,
        obs=data.obs,
        uae=active_org,
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

        add_filhos_etapa(
            session,
            etapa.id,
            tripulantes=etapa_in.tripulantes,
            oi_etapas=etapa_in.oi_etapas,
            pqd=etapa_in.pqd,
            revo=etapa_in.revo,
            heavy_cds=etapa_in.heavy_cds,
        )

    await session.commit()
    await session.refresh(new_missao)

    return success_response(
        data=MissaoPublic.model_validate(new_missao),
        message='Missão criada com sucesso',
    )


@router.put(
    '/{missao_id}/with-etapas',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoComEtapasDetailOut],
    dependencies=[UpdateMissaoEtp],
)
async def update_missao_with_etapas(
    missao_id: MissaoId,
    payload: MissaoComEtapasUpdate,
    session: Session,
    active_org: ActiveOrg,
) -> ApiResponse[MissaoComEtapasDetailOut]:
    """Atualiza missao + etapas atomicamente.

    Em qualquer falha (validacao, colisao, inexistencia) o
    SQLAlchemy faz rollback total da transacao. `is_simulador`
    e imutavel apos a criacao — nao e aceito no payload.
    """
    missao = await session.scalar(
        select(Missao).where(Missao.id == missao_id, Missao.uae == active_org)
    )
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada',
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
                    f'Etapa(s) não pertencem à missão '
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

    internal_trips: list[tuple[str, date, list[int], time, time]] = [
        (
            f'create[{i}]',
            e.data,
            [t.trip_id for t in e.tripulantes],
            e.dep,
            e.arr,
        )
        for i, e in enumerate(payload.create)
    ] + [
        (
            f'update[{i}](id={e.id})',
            e.data,
            [t.trip_id for t in e.tripulantes],
            e.dep,
            e.arr,
        )
        for i, e in enumerate(payload.update)
    ]
    try:
        assert_no_internal_trip_collision(internal_trips)
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

    # Escopo do ALVO: ver comentario equivalente no create com-etapas.
    try:
        await assert_tripulantes_da_org(
            session,
            trip_ids=[
                t.trip_id for _, e in payload_etapas for t in e.tripulantes
            ],
            uae=active_org,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Consistencia anv x tipo da missao (simulador usa aeronave is_sim).
    for label, e in payload_etapas:
        try:
            await assert_anv_simulador_consistency(
                session,
                pairs=[(e.anv, missao.is_simulador)],
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=f'{label}: {exc}',
            ) from exc

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
            etapa_col, uae_col = collision
            # Etapa de outra unidade: so a sigla da org, nunca id nem
            # horario (ver docs/ai/notes/rbac-e-isolamento.md).
            if uae_col == active_org:
                detalhe = (
                    f'{label}: colisao com etapa '
                    f'#{etapa_col.id} '
                    f'({etapa_col.dep.strftime("%H:%M")}-'
                    f'{etapa_col.arr.strftime("%H:%M")}) '
                    f'em {e.data.isoformat()}.'
                )
            else:
                detalhe = (
                    f'{label}: aeronave ja em uso por missao da '
                    f'{uae_col.upper()} em {e.data.isoformat()}.'
                )
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=detalhe,
            )

    # Colisao de tripulante contra o DB (exclui as etapas do proprio
    # payload, que serao removidas/reescritas nesta transacao).
    for label, e in payload_etapas:
        try:
            await assert_no_trip_collision(
                session,
                data=e.data,
                dep=e.dep,
                arr=e.arr,
                trip_ids=[t.trip_id for t in e.tripulantes],
                active_org=active_org,
                exclude_ids=exclude_ids,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=f'{label}: {exc}',
            ) from exc

    # 4. Patch direto (cliente sempre envia titulo/obs;
    #    semantica: PUT substitui, inclusive limpa pra None).
    missao.titulo = payload.titulo
    missao.obs = payload.obs

    # 5. Delete em lote: filhos primeiro, depois as proprias etapas.
    if payload.delete_ids:
        await limpar_filhos_de_etapas(session, payload.delete_ids)
        await session.execute(
            sa_delete(Etapa).where(Etapa.id.in_(payload.delete_ids))
        )
        await session.flush()

    # 6. Update em lote: delete bulk de OIs/Trips das etapas
    #    atualizadas, depois patch dos campos e re-insercao.
    if payload.update:
        await limpar_filhos_de_etapas(session, list(update_ids))
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
            add_filhos_etapa(
                session,
                e.id,
                tripulantes=e.tripulantes,
                oi_etapas=e.oi_etapas,
                pqd=e.pqd,
                revo=e.revo,
                heavy_cds=e.heavy_cds,
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
        add_filhos_etapa(
            session,
            new_etapa.id,
            tripulantes=e.tripulantes,
            oi_etapas=e.oi_etapas,
            pqd=e.pqd,
            revo=e.revo,
            heavy_cds=e.heavy_cds,
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
    pqd_data, revo_data, heavy_data = await fetch_especificos_data(
        session, etapa_ids
    )

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
                        'pqd': pqd_data.get(e.id, []),
                        'revo': revo_data.get(e.id, []),
                        'heavy_cds': heavy_data.get(e.id, []),
                    }
                )
                for e in etapas
            ],
        ),
        message='Missão atualizada com sucesso',
    )


@router.put(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoPublic],
    dependencies=[UpdateMissaoEtp],
)
async def update_missao(
    missao_id: MissaoId,
    missao_data: MissaoUpdate,
    session: Session,
    active_org: ActiveOrg,
) -> ApiResponse[MissaoPublic]:
    missao = await session.scalar(
        select(Missao).where(Missao.id == missao_id, Missao.uae == active_org)
    )
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada',
        )

    if missao_data.titulo is not None:
        missao.titulo = missao_data.titulo
    if missao_data.obs is not None:
        missao.obs = missao_data.obs

    await session.commit()
    await session.refresh(missao)

    return success_response(
        data=MissaoPublic.model_validate(missao),
        message='Missão atualizada com sucesso',
    )


@router.delete(
    '/{missao_id}/com-etapas',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
    dependencies=[DeleteMissaoEtp],
)
async def delete_missao_com_etapas(
    missao_id: MissaoId,
    session: Session,
    active_org: ActiveOrg,
) -> ApiResponse[None]:
    missao = await session.scalar(
        select(Missao).where(Missao.id == missao_id, Missao.uae == active_org)
    )
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada',
        )

    etapa_ids = list(
        await session.scalars(
            select(Etapa.id).where(Etapa.missao_id == missao_id)
        )
    )

    if etapa_ids:
        await limpar_filhos_de_etapas(session, etapa_ids)
        await session.execute(sa_delete(Etapa).where(Etapa.id.in_(etapa_ids)))

    await session.delete(missao)
    await session.commit()

    return success_response(
        message='Missão e etapas excluídas com sucesso',
    )


@router.delete(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
    dependencies=[DeleteMissaoEtp],
)
async def delete_missao(
    missao_id: MissaoId,
    session: Session,
    active_org: ActiveOrg,
) -> ApiResponse[None]:
    missao = await session.scalar(
        select(Missao).where(Missao.id == missao_id, Missao.uae == active_org)
    )
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada',
        )

    has_etapas = await session.scalar(
        select(Etapa.id).where(Etapa.missao_id == missao_id).limit(1)
    )
    if has_etapas:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Não é possível excluir missão com etapas vinculadas',
        )

    await session.delete(missao)
    await session.commit()

    return success_response(
        message='Missão excluída com sucesso',
    )
