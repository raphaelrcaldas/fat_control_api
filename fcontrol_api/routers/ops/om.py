"""Router para Ordem de Missão (OM)"""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.om import Etapa, OrdemMissao, TripulacaoOrdem
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.om import (
    OrdemMissaoCreate,
    OrdemMissaoList,
    OrdemMissaoOut,
    OrdemMissaoUpdate,
)
from fcontrol_api.schemas.pagination import PaginatedResponse
from fcontrol_api.security import get_current_user

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/om', tags=['ordens-missao'])


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=PaginatedResponse[OrdemMissaoList],
)
async def list_ordens(
    session: Session,
    page: int = 1,
    per_page: int = 20,
    status: Annotated[list[str] | None, Query()] = None,
    tipo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    busca: str | None = None,
):
    """
    Lista ordens de missão com filtros e paginação.

    - **status**: Lista de status (Rascunho, Elaborada, Finalizada, Revisada)
    - **tipo**: Tipo de missão
    - **data_inicio/data_fim**: Filtro por data de decolagem da primeira etapa
    - **busca**: Busca por número ou localidades
    """
    # Query base: apenas ordens não deletadas
    query = select(OrdemMissao).where(OrdemMissao.deleted_at.is_(None))

    # Filtro por status
    if status:
        query = query.where(OrdemMissao.status.in_(status))

    # Filtro por tipo
    if tipo:
        query = query.where(OrdemMissao.tipo.ilike(f'%{tipo}%'))

    # Filtro por busca (número da ordem ou código ICAO das etapas)
    if busca:
        busca_term = busca.upper()
        # Subquery para encontrar ordens que têm etapas com o código ICAO
        etapas_subquery = (
            select(Etapa.ordem_id)
            .where(
                (Etapa.origem.ilike(f'%{busca_term}%'))
                | (Etapa.dest.ilike(f'%{busca_term}%'))
            )
            .distinct()
        )
        query = query.where(
            (OrdemMissao.numero.ilike(f'%{busca}%'))
            | (OrdemMissao.id.in_(etapas_subquery))
        )

    # Contagem total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginação e ordenação
    query = (
        query.order_by(OrdemMissao.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await session.scalars(query)
    ordens = result.all()

    # Transformar para OrdemMissaoList
    items = [
        OrdemMissaoList(
            id=ordem.id,
            numero=ordem.numero,
            matricula_anv=ordem.matricula_anv,
            tipo=ordem.tipo,
            projeto=ordem.projeto,
            status=ordem.status,
            created_at=ordem.created_at,
            doc_ref=ordem.doc_ref,
        )
        for ordem in ordens
    ]

    pages = (total + per_page - 1) // per_page if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get('/{id}', status_code=HTTPStatus.OK, response_model=OrdemMissaoOut)
async def get_ordem(id: int, session: Session):
    """Busca uma ordem de missão por ID"""
    ordem = await session.scalar(
        select(OrdemMissao).where(
            OrdemMissao.id == id, OrdemMissao.deleted_at.is_(None)
        )
    )

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    return ordem


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=OrdemMissaoOut
)
async def create_ordem(
    ordem_data: OrdemMissaoCreate, session: Session, current_user: CurrentUser
):
    """Cria uma nova ordem de missão"""
    # Verificar se número já existe
    existing = await session.scalar(
        select(OrdemMissao).where(OrdemMissao.numero == ordem_data.numero)
    )
    if existing:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Já existe uma ordem com este número',
        )

    # Criar ordem (sempre como Rascunho na criação)
    ordem = OrdemMissao(
        numero=ordem_data.numero,
        matricula_anv=ordem_data.matricula_anv,
        tipo=ordem_data.tipo,
        created_by=current_user.id,
        projeto=ordem_data.projeto,
        status='Rascunho',  # Regra de negócio: nova ordem é sempre rascunho
        campos_especiais=[
            ce.model_dump() for ce in ordem_data.campos_especiais
        ],
        doc_ref=ordem_data.doc_ref,
    )

    session.add(ordem)
    await session.flush()  # Para obter o ID

    # Criar etapas
    for etapa_data in ordem_data.etapas:
        # Calcular tempo de voo: dt_arr - dt_dep em minutos
        tvoo_etp = int(
            (etapa_data.dt_arr - etapa_data.dt_dep).total_seconds() / 60
        )
        etapa = Etapa(
            ordem_id=ordem.id,
            dt_dep=etapa_data.dt_dep,
            origem=etapa_data.origem,
            dest=etapa_data.dest,
            dt_arr=etapa_data.dt_arr,
            alternativa=etapa_data.alternativa,
            tvoo_etp=tvoo_etp,
            tvoo_alt=etapa_data.tvoo_alt,
            qtd_comb=etapa_data.qtd_comb,
            esf_aer=etapa_data.esf_aer,
        )
        session.add(etapa)

    # Criar tripulação
    if ordem_data.tripulacao:
        for funcao, trip_ids in ordem_data.tripulacao.model_dump().items():
            for trip_id in trip_ids:
                trip_ordem = TripulacaoOrdem(
                    ordem_id=ordem.id,
                    tripulante_id=trip_id,
                    funcao=funcao,
                )
                session.add(trip_ordem)

    await session.commit()
    await session.refresh(ordem)

    return ordem


@router.put('/{id}', status_code=HTTPStatus.OK, response_model=OrdemMissaoOut)
async def update_ordem(
    id: int,
    ordem_data: OrdemMissaoUpdate,
    session: Session,
    current_user: CurrentUser,
):
    """Atualiza uma ordem de missão existente"""
    ordem = await session.scalar(
        select(OrdemMissao).where(
            OrdemMissao.id == id, OrdemMissao.deleted_at.is_(None)
        )
    )

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    # Verificar número duplicado
    if ordem_data.numero and ordem_data.numero != ordem.numero:
        existing = await session.scalar(
            select(OrdemMissao).where(
                OrdemMissao.numero == ordem_data.numero, OrdemMissao.id != id
            )
        )
        if existing:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Já existe uma ordem com este número',
            )

    # Atualizar campos simples
    update_data = ordem_data.model_dump(exclude_unset=True)

    # Tratar campos especiais
    if 'campos_especiais' in update_data:
        ordem.campos_especiais = (
            [ce.model_dump() for ce in ordem_data.campos_especiais]
            if ordem_data.campos_especiais
            else None
        )
        del update_data['campos_especiais']

    # Atualizar etapas se fornecidas
    if 'etapas' in update_data:
        # Remover etapas existentes
        for etapa in ordem.etapas:
            await session.delete(etapa)

        # Criar novas etapas
        for etapa_data in ordem_data.etapas or []:
            # Calcular tempo de voo: dt_arr - dt_dep em minutos
            tvoo_etp = int(
                (etapa_data.dt_arr - etapa_data.dt_dep).total_seconds() / 60
            )
            etapa = Etapa(
                ordem_id=ordem.id,
                dt_dep=etapa_data.dt_dep,
                origem=etapa_data.origem,
                dest=etapa_data.dest,
                dt_arr=etapa_data.dt_arr,
                alternativa=etapa_data.alternativa,
                tvoo_etp=tvoo_etp,
                tvoo_alt=etapa_data.tvoo_alt,
                qtd_comb=etapa_data.qtd_comb,
                esf_aer=etapa_data.esf_aer,
            )
            session.add(etapa)

        del update_data['etapas']

    # Atualizar tripulação se fornecida
    if 'tripulacao' in update_data:
        # Remover tripulação existente
        for trip in ordem.tripulacao:
            await session.delete(trip)

        # Criar nova tripulação
        if ordem_data.tripulacao:
            for funcao, trip_ids in ordem_data.tripulacao.model_dump().items():
                for trip_id in trip_ids:
                    trip_ordem = TripulacaoOrdem(
                        ordem_id=ordem.id,
                        tripulante_id=trip_id,
                        funcao=funcao,
                    )
                    session.add(trip_ordem)

        del update_data['tripulacao']

    # Atualizar demais campos
    for key, value in update_data.items():
        if value is not None:
            setattr(ordem, key, value)

    await session.commit()
    await session.refresh(ordem)

    return ordem


@router.delete('/{id}', status_code=HTTPStatus.OK)
async def delete_ordem(id: int, session: Session, current_user: CurrentUser):
    """Soft delete de uma ordem de missão"""
    ordem = await session.scalar(
        select(OrdemMissao).where(
            OrdemMissao.id == id, OrdemMissao.deleted_at.is_(None)
        )
    )

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    return {'detail': 'Ordem de missão excluída com sucesso'}
