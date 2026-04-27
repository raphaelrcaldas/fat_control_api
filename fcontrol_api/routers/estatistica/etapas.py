from datetime import date, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import func as sql_func
from sqlalchemy import literal_column, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
    TripEtapa,
)
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.estatistica.etapa import (
    EtapaCreate,
    EtapaDetailOut,
    EtapaExportRequest,
    EtapaFlatOut,
    EtapaOut,
    EtapaPublic,
    EtapaUpdate,
    MissaoComEtapasOut,
)
from fcontrol_api.schemas.funcoes import funcs
from fcontrol_api.schemas.response import (
    ApiPaginatedResponse,
    ApiResponse,
)
from fcontrol_api.services.etapas import (
    fetch_oi_detail_data,
    fetch_oi_etapas,
    fetch_trip_data,
    like_safe,
    list_etapas_flat,
)
from fcontrol_api.services.excel_etapas import generate_etapas_xlsx
from fcontrol_api.utils.responses import (
    paginated_response,
    success_response,
)

Session = Annotated[AsyncSession, Depends(get_session)]

EtapaId = Annotated[int, Path()]

router = APIRouter(prefix='/etapas', tags=['estatistica'])

_ETAPA_UPDATE_FIELDS = frozenset({
    'data',
    'origem',
    'destino',
    'dep',
    'arr',
    'anv',
    'pousos',
    'tow',
    'pax',
    'carga',
    'comb',
    'lub',
    'nivel',
    'sagem',
    'parte1',
    'obs',
})


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=(
        ApiPaginatedResponse[MissaoComEtapasOut]
        | ApiPaginatedResponse[EtapaFlatOut]
    ),
)
async def list_etapas(
    session: Session,
    data_ini: Annotated[date | None, Query()] = None,
    data_fim: Annotated[date | None, Query()] = None,
    origem: Annotated[str | None, Query(max_length=4)] = None,
    destino: Annotated[str | None, Query(max_length=4)] = None,
    anv: Annotated[list[str] | None, Query()] = None,
    esf_aer: Annotated[str | None, Query()] = None,
    reg: Annotated[str | None, Query(pattern='^[dnv]$')] = None,
    tipo_missao_cod: Annotated[list[str] | None, Query()] = None,
    trip_search: Annotated[str | None, Query()] = None,
    funcao: Annotated[funcs | None, Query()] = None,
    is_simulador: Annotated[bool, Query()] = False,
    flat: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=400)] = 20,
) -> (
    ApiPaginatedResponse[MissaoComEtapasOut]
    | ApiPaginatedResponse[EtapaFlatOut]
):
    """Lista etapas paginadas com filtros opcionais.

    `funcao` filtra etapas onde existe um TripEtapa cuja func
    casa com o codigo informado. Quando combinado com
    `trip_search`, ambas as condicoes precisam ser satisfeitas
    pelo MESMO TripEtapa (AND na mesma linha do JOIN).
    """
    # Passo 1: subquery de etapa_ids validos
    etapa_filter = select(Etapa.id)

    if data_ini:
        etapa_filter = etapa_filter.where(Etapa.data >= data_ini)
    if data_fim:
        etapa_filter = etapa_filter.where(Etapa.data <= data_fim)
    if origem:
        etapa_filter = etapa_filter.where(Etapa.origem.ilike(origem))
    if destino:
        etapa_filter = etapa_filter.where(Etapa.destino.ilike(destino))
    if anv:
        etapa_filter = etapa_filter.where(Etapa.anv.in_(anv))

    needs_oi_join = any([esf_aer, reg, tipo_missao_cod])
    if needs_oi_join:
        etapa_filter = etapa_filter.join(OIEtapa, OIEtapa.etapa_id == Etapa.id)
        if esf_aer:
            safe_esf = like_safe(esf_aer)
            etapa_filter = etapa_filter.join(
                EsforcoAereo,
                EsforcoAereo.id == OIEtapa.esf_aer_id,
            ).where(EsforcoAereo.descricao.ilike(f'%{safe_esf}%', escape='\\'))
        if reg:
            etapa_filter = etapa_filter.where(OIEtapa.reg == reg)
        if tipo_missao_cod:
            etapa_filter = etapa_filter.join(
                TipoMissao,
                TipoMissao.id == OIEtapa.tipo_missao_id,
            ).where(TipoMissao.cod.in_(tipo_missao_cod))

    if trip_search or funcao:
        etapa_filter = etapa_filter.join(
            TripEtapa, TripEtapa.etapa_id == Etapa.id
        )
        if trip_search:
            safe_trip = like_safe(trip_search)
            search_term = f'%{safe_trip}%'
            etapa_filter = (
                etapa_filter
                .join(
                    Tripulante,
                    Tripulante.id == TripEtapa.trip_id,
                )
                .join(User, User.id == Tripulante.user_id)
                .where(
                    User.nome_guerra.ilike(search_term, escape='\\')
                    | Tripulante.trig.ilike(search_term, escape='\\')
                )
            )
        if funcao:
            etapa_filter = etapa_filter.where(TripEtapa.func == funcao)

    if needs_oi_join or trip_search or funcao:
        etapa_filter = etapa_filter.distinct()

    valid_etapa_ids = etapa_filter.subquery()

    # Modo flat: paginacao por etapa individual
    if flat:
        return await list_etapas_flat(
            session,
            valid_etapa_ids,
            page,
            per_page,
        )

    # Passo 2: missao_ids distintos com paginacao
    has_filters = any([
        origem,
        destino,
        anv,
        esf_aer,
        reg,
        tipo_missao_cod,
        trip_search,
        funcao,
    ])

    missoes_com_etapa = (
        select(
            Etapa.missao_id.label('mid'),
            literal_column('1').label('ord'),
            sql_func.min(Etapa.data).label('first_date'),
        )
        .where(Etapa.id.in_(select(valid_etapa_ids.c.id)))
        .group_by(Etapa.missao_id)
    )

    missoes_com_etapa = missoes_com_etapa.join(
        Missao, Missao.id == Etapa.missao_id
    ).where(Missao.is_simulador.is_(is_simulador))

    if has_filters and not is_simulador:
        combined = missoes_com_etapa.subquery()
    else:
        missoes_sem_etapa_q = (
            select(
                Missao.id.label('mid'),
                literal_column('0').label('ord'),
                literal_column('NULL').label('first_date'),
            )
            .outerjoin(Etapa, Etapa.missao_id == Missao.id)
            .where(Etapa.id.is_(None))
        )
        if is_simulador:
            missoes_sem_etapa_q = missoes_sem_etapa_q.where(
                Missao.is_simulador.is_(True)
            )
        else:
            missoes_sem_etapa_q = missoes_sem_etapa_q.where(
                ~Missao.is_simulador
            )
        combined = union_all(missoes_sem_etapa_q, missoes_com_etapa).subquery()

    total = (
        await session.scalar(select(sql_func.count()).select_from(combined))
    ) or 0

    total_etapas = (
        await session.scalar(
            select(sql_func.count()).select_from(valid_etapa_ids)
        )
    ) or 0

    offset = (page - 1) * per_page
    paginated = (
        select(combined.c.mid)
        .order_by(
            combined.c.ord,
            combined.c.first_date.desc(),
            combined.c.mid.desc(),
        )
        .offset(offset)
        .limit(per_page)
    )
    missao_ids_result = await session.scalars(paginated)
    missao_ids_page = list(missao_ids_result.all())

    if not missao_ids_page:
        return paginated_response(
            items=[],
            total=total,
            page=page,
            per_page=per_page,
            total_items=total_etapas,
        )

    # Passo 3: etapas filtradas para os missao_ids
    etapas_query = (
        select(Etapa)
        .where(
            Etapa.missao_id.in_(missao_ids_page),
            Etapa.id.in_(select(valid_etapa_ids.c.id)),
        )
        .order_by(
            Etapa.missao_id,
            Etapa.data,
            Etapa.dep,
            Etapa.id,
        )
    )
    etapas_result = await session.scalars(etapas_query)
    etapas_all = etapas_result.all()

    # Passo 3b: OI etapas completas por etapa
    page_etapa_ids = [e.id for e in etapas_all]
    oi_detail_data = await fetch_oi_detail_data(
        session,
        page_etapa_ids,
    )

    # Passo 3c: tripulantes por etapa
    trip_data = await fetch_trip_data(session, page_etapa_ids)

    # Passo 4: objetos Missao e montagem da resposta
    missoes_result = await session.scalars(
        select(Missao)
        .where(Missao.id.in_(missao_ids_page))
        .order_by(Missao.id)
    )
    missoes = {m.id: m for m in missoes_result.all()}

    etapas_por_missao: dict[int, list[Etapa]] = {
        mid: [] for mid in missao_ids_page
    }
    for etapa in etapas_all:
        etapas_por_missao[etapa.missao_id].append(etapa)

    items = [
        MissaoComEtapasOut(
            id=missoes[mid].id,
            titulo=missoes[mid].titulo,
            obs=missoes[mid].obs,
            etapas=[
                EtapaOut.model_validate(e).model_copy(
                    update={
                        'oi_etapas': oi_detail_data.get(
                            e.id,
                            [],
                        ),
                        'tripulantes': trip_data.get(
                            e.id,
                            [],
                        ),
                    }
                )
                for e in etapas_por_missao[mid]
            ],
        )
        for mid in missao_ids_page
    ]

    return paginated_response(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_items=total_etapas,
    )


@router.get(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[EtapaDetailOut],
)
async def get_etapa_detail(
    id: EtapaId, session: Session
) -> ApiResponse[EtapaDetailOut]:
    etapa = await session.scalar(select(Etapa).where(Etapa.id == id))
    if not etapa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etapa nao encontrada',
        )

    oi_etapas = await fetch_oi_etapas(session, id)
    trip_data = await fetch_trip_data(session, [id])
    tripulantes = trip_data.get(id, [])

    detail = EtapaDetailOut.model_validate(etapa).model_copy(
        update={
            'tripulantes': tripulantes,
            'oi_etapas': oi_etapas,
        }
    )

    return success_response(data=detail)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[EtapaPublic],
)
async def create_etapa(
    data: EtapaCreate, session: Session
) -> ApiResponse[EtapaPublic]:
    """Cria uma nova etapa com tripulantes e OIs.

    tvoo eh campo Computed (arr - dep) — validamos o tvoo
    enviado pelo cliente para checar a soma das OIs.
    """
    if data.oi_etapas:
        soma_oi = sum(oi.tvoo for oi in data.oi_etapas)
        if soma_oi != data.tvoo:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=(
                    f'Soma dos tvoo das OIs ({soma_oi}) '
                    f'nao confere com tvoo da etapa '
                    f'({data.tvoo})'
                ),
            )

    etapa = Etapa(
        missao_id=data.missao_id,
        data=data.data,
        origem=data.origem.upper(),
        destino=data.destino.upper(),
        dep=data.dep,
        arr=data.arr,
        anv=data.anv,
        pousos=data.pousos,
        tow=data.tow,
        pax=data.pax,
        carga=data.carga,
        comb=data.comb,
        lub=data.lub,
        nivel=data.nivel,
        sagem=data.sagem,
        parte1=data.parte1,
        obs=data.obs,
    )
    session.add(etapa)
    await session.flush()

    for t in data.tripulantes:
        session.add(
            TripEtapa(
                etapa_id=etapa.id,
                func=t.func,
                func_bordo=t.func_bordo,
                trip_id=t.trip_id,
            )
        )

    for oi in data.oi_etapas:
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
    await session.refresh(etapa)
    return success_response(
        data=EtapaPublic.model_validate(etapa),
        message='Etapa criada com sucesso',
    )


@router.put(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[EtapaPublic],
)
async def update_etapa(
    id: EtapaId, data: EtapaUpdate, session: Session
) -> ApiResponse[EtapaPublic]:
    """Atualiza uma etapa existente.

    tvoo eh campo Computed — nao pode ser atualizado
    diretamente. Se oi_etapas fornecido, valida soma
    contra tvoo do payload ou do banco.
    """
    etapa = await session.scalar(select(Etapa).where(Etapa.id == id))
    if not etapa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etapa nao encontrada',
        )

    if data.oi_etapas is not None:
        tvoo_ref = data.tvoo if data.tvoo is not None else etapa.tvoo
        soma_oi = sum(oi.tvoo for oi in data.oi_etapas)
        if data.oi_etapas and soma_oi != tvoo_ref:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=(
                    f'Soma das OIs ({soma_oi} min) deve '
                    f'ser igual ao tvoo da etapa '
                    f'({tvoo_ref} min)'
                ),
            )

    updates = data.model_dump(exclude_unset=True)
    for key in ('tripulantes', 'oi_etapas', 'tvoo'):
        updates.pop(key, None)

    for campo, valor in updates.items():
        if campo not in _ETAPA_UPDATE_FIELDS:
            continue
        if campo == 'origem' and valor is not None:
            etapa.origem = valor.upper()
        elif campo == 'destino' and valor is not None:
            etapa.destino = valor.upper()
        else:
            setattr(etapa, campo, valor)

    if data.tripulantes is not None:
        await session.execute(
            sa_delete(TripEtapa).where(TripEtapa.etapa_id == id)
        )
        await session.flush()
        for t in data.tripulantes:
            session.add(
                TripEtapa(
                    etapa_id=id,
                    func=t.func,
                    func_bordo=t.func_bordo,
                    trip_id=t.trip_id,
                )
            )

    if data.oi_etapas is not None:
        await session.execute(sa_delete(OIEtapa).where(OIEtapa.etapa_id == id))
        await session.flush()
        for oi in data.oi_etapas:
            session.add(
                OIEtapa(
                    etapa_id=id,
                    esf_aer_id=oi.esf_aer_id,
                    tipo_missao_id=oi.tipo_missao_id,
                    reg=oi.reg,
                    tvoo=oi.tvoo,
                )
            )

    await session.commit()
    await session.refresh(etapa)
    return success_response(
        data=EtapaPublic.model_validate(etapa),
        message='Etapa atualizada com sucesso',
    )


@router.delete(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
)
async def delete_etapa(id: EtapaId, session: Session) -> ApiResponse[None]:
    """Remove uma etapa e seus dados vinculados."""
    etapa = await session.scalar(select(Etapa).where(Etapa.id == id))
    if not etapa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etapa nao encontrada',
        )

    await session.execute(sa_delete(TripEtapa).where(TripEtapa.etapa_id == id))
    await session.execute(sa_delete(OIEtapa).where(OIEtapa.etapa_id == id))

    await session.delete(etapa)
    await session.commit()
    return success_response(
        message='Etapa excluida com sucesso',
    )


@router.post('/export')
async def export_etapas(
    data: EtapaExportRequest,
    session: Session,
) -> StreamingResponse:
    """Exporta etapas selecionadas para Excel."""
    etapas_result = await session.scalars(
        select(Etapa)
        .where(Etapa.id.in_(data.ids))
        .order_by(Etapa.data, Etapa.dep, Etapa.id)
    )
    etapas = list(etapas_result.all())

    if not etapas:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Nenhuma etapa encontrada',
        )

    etapa_ids = [e.id for e in etapas]

    oi_data = None
    if data.esforco_aereo:
        oi_data = await fetch_oi_detail_data(
            session,
            etapa_ids,
        )

    trip_data = None
    if data.tripulantes:
        trip_data = await fetch_trip_data(
            session,
            etapa_ids,
        )

    columns = {
        'pousos': data.pousos,
        'nivel': data.nivel,
        'tow': data.tow,
        'pax': data.pax,
        'carga': data.carga,
        'comb': data.comb,
        'lub': data.lub,
        'esforco_aereo': data.esforco_aereo,
        'tripulantes': data.tripulantes,
    }

    buffer = generate_etapas_xlsx(
        etapas=etapas,
        oi_data=oi_data,
        trip_data=trip_data,
        columns=columns,
    )

    now = datetime.now()
    filename = f'etapas_1_1_GT_{now:%d%m%Y}.xlsx'

    return StreamingResponse(
        content=buffer,
        media_type=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
        headers={
            'Content-Disposition': (f'attachment; filename="{filename}"'),
        },
    )
