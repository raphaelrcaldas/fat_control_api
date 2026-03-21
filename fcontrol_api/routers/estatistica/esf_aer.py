from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, delete, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.esf_aer import (
    EsfAerAloc,
    EsfAerAlocHist,
    EsforcoAereo,
)
from fcontrol_api.models.estatistica.etapa import Etapa, OIEtapa
from fcontrol_api.schemas.estatistica.esf_aer import (
    EsfAerDiffRow,
    EsfAerImportResponse,
    EsfAerItem,
    EsfAerResumoItem,
    EsfAerResumoResponse,
    EsfAerUpdateRequest,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
AnoRef = Annotated[int, Query(ge=2020)]

router = APIRouter(prefix='/esfaer', tags=['estatistica'])


def _meses_kwargs(meses: list[int]) -> dict[str, int]:
    """Mapeia lista de 12 valores para kwargs m1..m12."""
    return {f'm{i + 1}': meses[i] for i in range(12)}


@router.get(
    '/list',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[EsfAerItem]],
)
async def list_esf_aer_items(session: Session):
    """Lista todos os itens de Esforco Aereo para selects."""
    result = await session.execute(
        select(
            EsforcoAereo.id,
            EsforcoAereo.descricao,
        ).order_by(EsforcoAereo.descricao)
    )
    rows = result.all()
    return success_response(
        data=[
            EsfAerItem(id=row.id, descricao=row.descricao)
            for row in rows
        ]
    )


def _mes_col(mes: int):
    """Gera coluna SUM condicional para um mes."""
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
    voado_cols = [_mes_col(m) for m in range(1, 13)]
    sagem_cols = [
        func.coalesce(
            getattr(EsfAerAloc, f'm{i}'), 0
        ).label(f'sagem_m{i}')
        for i in range(1, 13)
    ]

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
            *voado_cols,
            *sagem_cols,
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
            *[
                getattr(EsfAerAloc, f'm{i}')
                for i in range(1, 13)
            ],
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
    total_meses_voados = [0] * 12
    total_meses_sagem = [0] * 12

    for row in rows:
        alocado = row.alocado
        voado = row.voado
        meses_voados = [
            getattr(row, f'm{m}') for m in range(1, 13)
        ]
        meses_sagem = [
            getattr(row, f'sagem_m{m}') for m in range(1, 13)
        ]

        items.append(
            EsfAerResumoItem(
                id=row.id,
                descricao=row.descricao,
                alocado=alocado,
                voado=voado,
                saldo=alocado - voado,
                meses_sagem=meses_sagem,
                meses_voados=meses_voados,
            )
        )

        total_alocado += alocado
        total_voado += voado
        for i in range(12):
            total_meses_voados[i] += meses_voados[i]
            total_meses_sagem[i] += meses_sagem[i]

    return success_response(
        data=EsfAerResumoResponse(
            items=items,
            total_alocado=total_alocado,
            total_voado=total_voado,
            total_saldo=total_alocado - total_voado,
            total_meses_sagem=total_meses_sagem,
            total_meses_voados=total_meses_voados,
        )
    )


def _esf_aer_key(
    tipo: str,
    modelo: str,
    grupo: str,
    prog: str,
    sub_prog: str | None,
    aplicacao: str | None,
) -> tuple[str, ...]:
    """Chave unica para identificar um EsforcoAereo."""
    return (
        tipo.strip(),
        modelo.strip(),
        grupo.strip(),
        prog.strip(),
        (sub_prog or '').strip(),
        (aplicacao or '').strip(),
    )


@router.put(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[EsfAerImportResponse],
)
async def update_esf_aer(
    session: Session,
    payload: EsfAerUpdateRequest,
):
    """Importa/atualiza Esforco Aereo em lote."""
    ano_ref = payload.ano_ref

    # 1. Buscar todos os EsforcoAereo existentes
    existing_result = await session.execute(select(EsforcoAereo))
    existing_rows = existing_result.scalars().all()

    # Mapa: chave -> EsforcoAereo
    db_map: dict[tuple[str, ...], EsforcoAereo] = {
        _esf_aer_key(
            r.tipo,
            r.modelo,
            r.grupo,
            r.prog,
            r.sub_prog,
            r.aplicacao,
        ): r
        for r in existing_rows
    }

    # 2. Buscar alocacoes existentes para o ano
    aloc_result = await session.execute(
        select(EsfAerAloc).where(EsfAerAloc.ano_ref == ano_ref)
    )
    aloc_rows = aloc_result.scalars().all()

    # Mapa: esfaer_id -> EsfAerAloc
    aloc_map: dict[int, EsfAerAloc] = {
        a.esfaer_id: a for a in aloc_rows
    }

    # Mapa auxiliar: esfaer_id -> EsforcoAereo
    id_to_esf = {r.id: r for r in existing_rows}

    # 3. Processar cada item do payload
    diff_rows: list[EsfAerDiffRow] = []
    import_ids: set[int] = set()

    for item in payload.items:
        key = _esf_aer_key(
            item.tipo,
            item.modelo,
            item.grupo,
            item.programa,
            item.subprograma,
            item.aplicacao,
        )

        meses_kw = _meses_kwargs(item.meses_sagem)

        # 3a. EsforcoAereo novo?
        if key not in db_map:
            novo = EsforcoAereo(
                tipo=item.tipo.strip(),
                modelo=item.modelo.strip(),
                grupo=item.grupo.strip(),
                prog=item.programa.strip(),
                sub_prog=item.subprograma.strip() or None,
                aplicacao=item.aplicacao.strip() or None,
            )
            session.add(novo)
            await session.flush()
            db_map[key] = novo
            id_to_esf[novo.id] = novo

            nova_aloc = EsfAerAloc(
                esfaer_id=novo.id,
                ano_ref=ano_ref,
                alocado=item.horas_alocadas,
                **meses_kw,
            )
            session.add(nova_aloc)
            aloc_map[novo.id] = nova_aloc
            import_ids.add(novo.id)
            diff_rows.append(
                EsfAerDiffRow(
                    descricao=novo.descricao,
                    antes=None,
                    depois=item.horas_alocadas,
                )
            )
            continue

        esf = db_map[key]
        import_ids.add(esf.id)
        antes = (
            aloc_map[esf.id].alocado if esf.id in aloc_map else 0
        )

        # 3b. Alocacao existente para este ano?
        if esf.id in aloc_map:
            aloc = aloc_map[esf.id]
            if aloc.alocado != item.horas_alocadas:
                aloc.alocado = item.horas_alocadas
            for i in range(12):
                setattr(aloc, f'm{i + 1}', item.meses_sagem[i])
        else:
            nova_aloc = EsfAerAloc(
                esfaer_id=esf.id,
                ano_ref=ano_ref,
                alocado=item.horas_alocadas,
                **meses_kw,
            )
            session.add(nova_aloc)
            aloc_map[esf.id] = nova_aloc

        diff_rows.append(
            EsfAerDiffRow(
                descricao=esf.descricao,
                antes=antes,
                depois=item.horas_alocadas,
            )
        )

    # 4. Detectar removidos (tinham alocacao no banco, nao vieram)
    removed_ids: list[int] = []

    for esfaer_id, aloc in aloc_map.items():
        if esfaer_id not in import_ids:
            esf = id_to_esf.get(esfaer_id)
            descricao = (
                esf.descricao if esf else f'ID {esfaer_id}'
            )
            diff_rows.append(
                EsfAerDiffRow(
                    descricao=descricao,
                    antes=aloc.alocado,
                    depois=None,
                )
            )
            removed_ids.append(aloc.id)

    if removed_ids:
        await session.execute(
            delete(EsfAerAloc).where(
                EsfAerAloc.id.in_(removed_ids)
            )
        )

    # 5. Registrar historico para alocacoes que mudaram
    await session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    desc_to_esfaer: dict[str, int] = {
        e.descricao: e.id
        for e in list(id_to_esf.values())
        + list(db_map.values())
    }
    for row in diff_rows:
        if row.antes == row.depois:
            continue
        esfaer_id = desc_to_esfaer.get(row.descricao)
        if esfaer_id is None:
            continue
        aloc = aloc_map.get(esfaer_id)
        if aloc is None or aloc.id in removed_ids:
            continue
        session.add(
            EsfAerAlocHist(
                esf_aer_aloc_id=aloc.id,
                aloc_hist=row.antes or 0,
                timestamp=now,
            )
        )

    await session.commit()

    changed = [r for r in diff_rows if r.antes != r.depois]
    changed.sort(key=lambda r: r.descricao)

    # Total do esquadrao (todas as alocacoes, sem simulador)
    all_esf: dict[int, EsforcoAereo] = {**id_to_esf}
    for v in db_map.values():
        all_esf[v.id] = v

    removed_set = set(removed_ids)
    total_antes = sum(
        r.antes or 0
        for r in diff_rows
        if 'SML' not in r.descricao
    )
    total_depois = 0
    for eid, aloc in aloc_map.items():
        if aloc.id in removed_set:
            continue
        esf = all_esf.get(eid)
        if esf and 'SML' in esf.descricao:
            continue
        total_depois += aloc.alocado

    return success_response(
        data=EsfAerImportResponse(
            ano_ref=ano_ref,
            rows=changed,
            total_antes=total_antes,
            total_depois=total_depois,
        )
    )
