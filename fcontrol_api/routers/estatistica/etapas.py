from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
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
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.estatistica.etapa import (
    EtapaCreate,
    EtapaDetailOut,
    EtapaOut,
    EtapaPublic,
    EtapaUpdate,
    MissaoComEtapasOut,
    OIEtapaOut,
    TripEtapaOut,
)
from fcontrol_api.schemas.response import (
    ApiPaginatedResponse,
    ApiResponse,
)
from fcontrol_api.utils.responses import (
    paginated_response,
    success_response,
)

Session = Annotated[AsyncSession, Depends(get_session)]

EtapaId = Annotated[int, Path()]

router = APIRouter(prefix='/etapas', tags=['estatistica'])


def _like_safe(val: str) -> str:
    """Escapa caracteres especiais de LIKE no valor fornecido."""
    return val.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _oi_extra(
    etapa_id: int,
    oi_data: dict[int, dict[str, list[str]]],
) -> dict[str, object]:
    info = oi_data.get(etapa_id)
    if not info:
        return {'esf_aer_itens': [], 'tipo_missao_cod': None}
    return {
        'esf_aer_itens': list(dict.fromkeys(info['esf_aer'])),
        'tipo_missao_cod': info['tipo'][0] if info['tipo'] else None,
    }


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiPaginatedResponse[MissaoComEtapasOut],
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
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
):
    # Passo 1: subquery de etapa_ids válidos
    # JOINs com OIEtapa e TripEtapa são condicionais — apenas quando
    # o filtro correspondente é fornecido, evitando multiplicação de linhas.
    # DISTINCT é necessário quando há JOIN com OIEtapa (1 etapa → N OIEtapa).
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
            safe_esf = _like_safe(esf_aer)
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

    if trip_search:
        safe_trip = _like_safe(trip_search)
        search_term = f'%{safe_trip}%'
        etapa_filter = (
            etapa_filter
            .join(TripEtapa, TripEtapa.etapa_id == Etapa.id)
            .join(Tripulante, Tripulante.id == TripEtapa.trip_id)
            .join(User, User.id == Tripulante.user_id)
            .where(
                User.nome_guerra.ilike(search_term, escape='\\')
                | Tripulante.trig.ilike(search_term, escape='\\')
            )
        )

    if needs_oi_join or trip_search:
        etapa_filter = etapa_filter.distinct()

    valid_etapa_ids = etapa_filter.subquery()

    # Passo 2: missao_ids distintos com paginação
    # Sem filtros: missões sem etapas aparecem no topo (order=0),
    # seguidas pelas com etapas (order=1).
    has_filters = any([
        data_ini,
        data_fim,
        origem,
        destino,
        anv,
        esf_aer,
        reg,
        tipo_missao_cod,
        trip_search,
    ])

    missoes_com_etapa = (
        select(
            Etapa.missao_id.label('mid'),
            literal_column('1').label('ord'),
        )
        .where(Etapa.id.in_(select(valid_etapa_ids.c.id)))
        .distinct()
    )

    if has_filters:
        combined = missoes_com_etapa.subquery()
    else:
        missoes_sem_etapa = (
            select(
                Missao.id.label('mid'),
                literal_column('0').label('ord'),
            )
            .outerjoin(Etapa, Etapa.missao_id == Missao.id)
            .where(Etapa.id.is_(None))
        )
        combined = union_all(missoes_sem_etapa, missoes_com_etapa).subquery()

    total = (
        await session.scalar(select(sql_func.count()).select_from(combined))
    ) or 0

    offset = (page - 1) * per_page
    paginated = (
        select(combined.c.mid)
        .order_by(combined.c.ord, combined.c.mid.desc())
        .offset(offset)
        .limit(per_page)
    )
    missao_ids_result = await session.scalars(paginated)
    missao_ids_page = list(missao_ids_result.all())

    if not missao_ids_page:
        return paginated_response(
            items=[], total=total, page=page, per_page=per_page
        )

    # Passo 3: etapas filtradas para os missao_ids da página
    # Reutiliza os mesmos filtros, garantindo que cada Missao exiba
    # apenas as etapas que passaram nos critérios, não todas as suas
    # etapas. Missões sem etapas terão lista vazia.
    etapas_query = (
        select(Etapa)
        .where(
            Etapa.missao_id.in_(missao_ids_page),
            Etapa.id.in_(select(valid_etapa_ids.c.id)),
        )
        .order_by(Etapa.missao_id, Etapa.data, Etapa.dep, Etapa.id)
    )
    etapas_result = await session.scalars(etapas_query)
    etapas_all = etapas_result.all()

    # Passo 3b: esf_aer e tipo_missao por etapa (exibição na tabela)
    page_etapa_ids = [e.id for e in etapas_all]
    oi_data: dict[int, dict[str, list[str]]] = {}
    if page_etapa_ids:
        oi_rows = await session.execute(
            select(
                OIEtapa.etapa_id,
                EsforcoAereo.descricao.label('esf_descr'),
                TipoMissao.cod.label('tipo_cod'),
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
            .where(OIEtapa.etapa_id.in_(page_etapa_ids))
            .order_by(OIEtapa.etapa_id, OIEtapa.id)
        )
        for row in oi_rows.all():
            eid = row.etapa_id
            if eid not in oi_data:
                oi_data[eid] = {'esf_aer': [], 'tipo': []}
            oi_data[eid]['esf_aer'].append(row.esf_descr)
            oi_data[eid]['tipo'].append(row.tipo_cod)

    # Passo 3c: tripulantes por etapa (func -> [trig])
    trip_data: dict[int, dict[str, list[str]]] = {}
    if page_etapa_ids:
        trip_rows = await session.execute(
            select(
                TripEtapa.etapa_id,
                TripEtapa.func,
                Tripulante.trig,
            )
            .select_from(TripEtapa)
            .join(
                Tripulante,
                Tripulante.id == TripEtapa.trip_id,
            )
            .where(TripEtapa.etapa_id.in_(page_etapa_ids))
            .order_by(TripEtapa.etapa_id, TripEtapa.id)
        )
        for row in trip_rows.all():
            eid = row.etapa_id
            if eid not in trip_data:
                trip_data[eid] = {}
            trip_data[eid].setdefault(row.func, []).append(row.trig)

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
                        **_oi_extra(e.id, oi_data),
                        'tripulantes': trip_data.get(e.id, {}),
                    }
                )
                for e in etapas_por_missao[mid]
            ],
        )
        for mid in missao_ids_page
    ]

    return paginated_response(
        items=items, total=total, page=page, per_page=per_page
    )


@router.get(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[EtapaDetailOut],
)
async def get_etapa_detail(id: EtapaId, session: Session):
    etapa = await session.scalar(select(Etapa).where(Etapa.id == id))
    if not etapa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etapa nao encontrada',
        )

    # OI data estruturada (cada OIEtapa com esf_aer, tipo, reg, tvoo)
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
        .where(OIEtapa.etapa_id == id)
        .order_by(OIEtapa.id)
    )
    oi_etapas = [
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

    # Dados flat para campos herdados de EtapaOut
    oi_data: dict[int, dict[str, list[str]]] = {}
    if oi_etapas:
        oi_data[id] = {
            'esf_aer': list(dict.fromkeys(oi.esf_aer for oi in oi_etapas)),
            'tipo': [oi_etapas[0].tipo_missao_cod],
        }

    # Tripulantes da etapa
    trip_rows = await session.execute(
        select(
            TripEtapa.trip_id,
            TripEtapa.func,
            TripEtapa.func_bordo,
            Tripulante.trig,
            User.nome_guerra,
            User.p_g,
        )
        .select_from(TripEtapa)
        .join(Tripulante, Tripulante.id == TripEtapa.trip_id)
        .join(User, User.id == Tripulante.user_id)
        .where(TripEtapa.etapa_id == id)
        .order_by(TripEtapa.id)
    )
    tripulantes = [
        TripEtapaOut(
            trip_id=row.trip_id,
            trig=row.trig,
            nome_guerra=row.nome_guerra,
            p_g=row.p_g,
            func=row.func,
            func_bordo=row.func_bordo,
        )
        for row in trip_rows.all()
    ]

    detail = EtapaDetailOut.model_validate(etapa).model_copy(
        update={
            **_oi_extra(etapa.id, oi_data),
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
async def create_etapa(data: EtapaCreate, session: Session):
    """Cria uma nova etapa com tripulantes e OIs.

    tvoo eh campo Computed (arr - dep) — validamos o tvoo enviado
    pelo cliente para checar a soma das OIs.
    """
    if data.oi_etapas:
        soma_oi = sum(oi.tvoo for oi in data.oi_etapas)
        if soma_oi != data.tvoo:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                detail=(
                    f'Soma dos tvoo das OIs ({soma_oi}) '
                    f'nao confere com tvoo da etapa ({data.tvoo})'
                ),
            )

    # tvoo e campo Computed — nao passa ao construtor
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
async def update_etapa(id: EtapaId, data: EtapaUpdate, session: Session):
    """Atualiza uma etapa existente.

    tvoo eh campo Computed — nao pode ser atualizado diretamente.
    Se oi_etapas fornecido, valida soma contra tvoo do payload ou
    do banco quando tvoo nao for enviado no payload.
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
                    f'Soma das OIs ({soma_oi} min) deve ser igual '
                    f'ao tvoo da etapa ({tvoo_ref} min)'
                ),
            )

    # Aplicar apenas campos enviados explicitamente no payload
    updates = data.model_dump(exclude_unset=True)
    for key in ('tripulantes', 'oi_etapas', 'tvoo'):
        updates.pop(key, None)

    for campo, valor in updates.items():
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
async def delete_etapa(id: EtapaId, session: Session):
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
    return success_response(message='Etapa excluida com sucesso')
