"""Router para Ordem de Missão (OM)"""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.etiquetas import Etiqueta
from fcontrol_api.models.public.om import Etapa, OrdemMissao, TripulacaoOrdem
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.etiquetas import (
    EtiquetaCreate,
    EtiquetaSchema,
    EtiquetaUpdate,
)
from fcontrol_api.schemas.om import (
    EtapaListItem,
    OrdemMissaoCreate,
    OrdemMissaoList,
    OrdemMissaoUpdate,
)
from fcontrol_api.schemas.pagination import PaginatedResponse
from fcontrol_api.security import get_current_user

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/om', tags=['ordens-missao'])


def escape_like(value: str) -> str:
    """Escapa caracteres especiais para ILIKE (%, _, \\)."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


async def get_ordem_with_relations(
    session: AsyncSession, ordem_id: int
) -> OrdemMissao | None:
    """Busca ordem com relacionamentos carregados."""
    result = await session.execute(
        select(OrdemMissao)
        .where(OrdemMissao.id == ordem_id, OrdemMissao.deleted_at.is_(None))
        .options(
            selectinload(OrdemMissao.etapas),
            selectinload(OrdemMissao.tripulacao)
            .selectinload(TripulacaoOrdem.tripulante)
            .selectinload(Tripulante.user),
            selectinload(OrdemMissao.etiquetas),
        )
    )
    return result.scalar_one_or_none()


def build_ordem_response(ordem: OrdemMissao) -> dict:
    """Constrói resposta da ordem com tripulação formatada."""
    tripulacao = []
    for t in ordem.tripulacao:
        trip = t.tripulante
        tripulacao.append({
            'id': t.id,
            'tripulante_id': t.tripulante_id,
            'funcao': t.funcao,
            'p_g': t.p_g,  # Snapshot do posto/graduacao na OM
            'tripulante': {
                'id': trip.id,
                'trig': trip.trig,
                'p_g': trip.user.p_g if trip and trip.user else '',
                'nome_guerra': (
                    trip.user.nome_guerra if trip and trip.user else ''
                ),
                'nome_completo': (
                    trip.user.nome_completo if trip and trip.user else ''
                ),
            }
            if trip
            else None,
        })

    return {
        'id': ordem.id,
        'numero': ordem.numero,
        'matricula_anv': ordem.matricula_anv,
        'tipo': ordem.tipo,
        'projeto': ordem.projeto,
        'status': ordem.status,
        'campos_especiais': ordem.campos_especiais or [],
        'doc_ref': ordem.doc_ref,
        'data_saida': ordem.data_saida,
        'uae': ordem.uae,
        'created_by': ordem.created_by,
        'created_at': ordem.created_at,
        'updated_at': ordem.updated_at,
        'deleted_at': ordem.deleted_at,
        'etapas': [
            {
                'id': e.id,
                'ordem_id': e.ordem_id,
                'dt_dep': e.dt_dep,
                'origem': e.origem,
                'dest': e.dest,
                'dt_arr': e.dt_arr,
                'alternativa': e.alternativa,
                'tvoo_etp': e.tvoo_etp,
                'tvoo_alt': e.tvoo_alt,
                'qtd_comb': e.qtd_comb,
                'esf_aer': e.esf_aer,
            }
            for e in ordem.etapas
        ],
        'tripulacao': tripulacao,
        'etiquetas': [
            {
                'id': et.id,
                'nome': et.nome,
                'cor': et.cor,
                'descricao': et.descricao,
            }
            for et in ordem.etiquetas
        ],
    }


async def _criar_tripulacao_batch(
    session: AsyncSession, ordem_id: int, tripulacao_data
) -> None:
    """
    Cria registros de tripulacao usando batch query para evitar N+1.

    Args:
        session: Sessao do banco de dados
        ordem_id: ID da ordem de missao
        tripulacao_data: Dados da tripulacao (TripulacaoOM schema)
    """
    # Coletar todos os IDs de tripulantes
    all_trip_ids = []
    tripulacao_dict = tripulacao_data.model_dump()
    for trip_ids in tripulacao_dict.values():
        all_trip_ids.extend(trip_ids)

    if not all_trip_ids:
        return

    # Uma unica query para buscar todos os tripulantes
    tripulantes_result = await session.scalars(
        select(Tripulante)
        .where(Tripulante.id.in_(all_trip_ids))
        .options(selectinload(Tripulante.user))
    )
    tripulantes_map = {t.id: t for t in tripulantes_result.all()}

    # Criar registros de tripulacao usando o map
    for funcao, trip_ids in tripulacao_dict.items():
        for trip_id in trip_ids:
            tripulante = tripulantes_map.get(trip_id)
            if not tripulante or not tripulante.user:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f'Tripulante {trip_id} não encontrado',
                )
            trip_ordem = TripulacaoOrdem(
                ordem_id=ordem_id,
                tripulante_id=trip_id,
                funcao=funcao,
                p_g=tripulante.user.p_g,  # Snapshot do p_g atual
            )
            session.add(trip_ordem)


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
    status_ne: str | None = None,
    tipo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    busca: str | None = None,
    etiquetas_ids: Annotated[list[int] | None, Query()] = None,
):
    """
    Lista ordens de missão com filtros e paginação.

    - **status**: Lista de status para incluir
    - **status_ne**: Status para excluir (not equal, ex: rascunho)
    - **tipo**: Tipo de missão
    - **data_inicio/data_fim**: Filtro por data de decolagem da primeira etapa
    - **busca**: Busca por número ou localidades
    """
    # Query base: apenas ordens não deletadas
    query = select(OrdemMissao).where(OrdemMissao.deleted_at.is_(None))

    # Filtro por status (inclusão ou exclusão)
    if status:
        query = query.where(OrdemMissao.status.in_(status))
    elif status_ne:
        query = query.where(OrdemMissao.status != status_ne)

    # Filtro por tipo (com escape de caracteres especiais ILIKE)
    if tipo:
        escaped_tipo = escape_like(tipo)
        query = query.where(
            OrdemMissao.tipo.ilike(f'%{escaped_tipo}%', escape='\\')
        )

    # Filtro por busca (número da ordem ou código ICAO das etapas)
    if busca:
        escaped_busca = escape_like(busca)
        escaped_busca_upper = escape_like(busca.upper())
        # Subquery para encontrar ordens que têm etapas com o código ICAO
        etapas_subquery = (
            select(Etapa.ordem_id)
            .where(
                (Etapa.origem.ilike(f'%{escaped_busca_upper}%', escape='\\'))
                | (Etapa.dest.ilike(f'%{escaped_busca_upper}%', escape='\\'))
            )
            .distinct()
        )
        query = query.where(
            (OrdemMissao.numero.ilike(f'%{escaped_busca}%', escape='\\'))
            | (OrdemMissao.id.in_(etapas_subquery))
        )

    # Filtro por etiquetas
    if etiquetas_ids:
        query = query.where(
            OrdemMissao.etiquetas.any(Etiqueta.id.in_(etiquetas_ids))
        )

    # Contagem total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginação e ordenação com eager load de etapas
    query = (
        query.order_by(OrdemMissao.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(
            selectinload(OrdemMissao.etapas),
            selectinload(OrdemMissao.etiquetas),
        )
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
            data_saida=ordem.data_saida,
            uae=ordem.uae,
            etapas=[
                EtapaListItem(
                    dt_dep=e.dt_dep,
                    origem=e.origem,
                    dest=e.dest,
                )
                for e in ordem.etapas
            ],
            etiquetas=[
                {
                    'id': et.id,
                    'nome': et.nome,
                    'cor': et.cor,
                    'descricao': et.descricao,
                }
                for et in ordem.etiquetas
            ],
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


@router.get('/{id}', status_code=HTTPStatus.OK)
async def get_ordem(id: int, session: Session):
    """Busca uma ordem de missão por ID"""
    ordem = await get_ordem_with_relations(session, id)

    if not ordem:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Ordem de missão não encontrada',
        )

    return build_ordem_response(ordem)


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_ordem(
    ordem_data: OrdemMissaoCreate, session: Session, current_user: CurrentUser
):
    """Cria uma nova ordem de missão"""

    # Calcular data_saida (data da primeira etapa)
    data_saida = None
    if ordem_data.etapas:
        data_saida = min(e.dt_dep for e in ordem_data.etapas).date()

    # Criar ordem (sempre como rascunho na criação)
    ordem = OrdemMissao(
        numero='auto',  # Regra de negócio: nova ordem é sempre auto
        matricula_anv=ordem_data.matricula_anv,
        tipo=ordem_data.tipo,
        created_by=current_user.id,
        projeto=ordem_data.projeto,
        status='rascunho',  # Regra de negócio: nova ordem é sempre rascunho
        campos_especiais=[
            ce.model_dump() for ce in ordem_data.campos_especiais
        ],
        doc_ref=ordem_data.doc_ref,
        data_saida=data_saida,
        uae=ordem_data.uae,
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

    # Criar tripulação (batch query para evitar N+1)
    if ordem_data.tripulacao:
        await _criar_tripulacao_batch(session, ordem.id, ordem_data.tripulacao)

    # Vincular etiquetas
    if ordem_data.etiquetas_ids:
        etiquetas_result = await session.execute(
            select(Etiqueta).where(Etiqueta.id.in_(ordem_data.etiquetas_ids))
        )
        ordem.etiquetas = list(etiquetas_result.scalars().all())

    await session.commit()

    # Buscar ordem com relacionamentos carregados para retorno
    ordem_loaded = await get_ordem_with_relations(session, ordem.id)
    return build_ordem_response(ordem_loaded)


@router.put('/{id}', status_code=HTTPStatus.OK)
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

    # Identificar transição para aprovada para gerar número
    if (
        ordem_data.status == 'aprovada'
        and ordem.status == 'rascunho'
        and (ordem.numero == 'auto' or not ordem.numero)
    ):
        # Garantir que temos a data_saida
        if ordem_data.etapas:
            ordem.data_saida = min(e.dt_dep for e in ordem_data.etapas).date()
        elif ordem.etapas:
            ordem.data_saida = min(e.dt_dep for e in ordem.etapas).date()

        if not ordem.data_saida:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='A ordem deve ter pelo menos uma etapa',
            )

        # 2. Consultar quantas OMs numeradas existem no ano/UAE
        year = ordem.data_saida.year
        target_uae = ordem.uae

        count = await session.scalar(
            select(func.count(OrdemMissao.id)).where(
                OrdemMissao.numero != 'auto',
                OrdemMissao.deleted_at.is_(None),
                extract('year', OrdemMissao.data_saida) == year,
                OrdemMissao.uae == target_uae,
            )
        )

        # 3. Atribuir número sequencial
        seq = (count or 0) + 1
        ordem.numero = f'{seq:03d}'

        # Garantir que temos o target_year e target_uae
        target_year = None
        target_uae = ordem.uae
        if ordem_data.etapas:
            target_year = min(e.dt_dep for e in ordem_data.etapas).year
        elif ordem.data_saida:
            target_year = ordem.data_saida.year

        if target_year and target_uae:
            existing = await session.scalar(
                select(OrdemMissao).where(
                    OrdemMissao.numero == ordem.numero,
                    OrdemMissao.id != id,
                    OrdemMissao.deleted_at.is_(None),
                    extract('year', OrdemMissao.data_saida) == target_year,
                    OrdemMissao.uae == target_uae,
                )
            )
            if existing:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=(
                        f'Já existe uma ordem com este número '
                        f'no ano {target_year} para a UAE {target_uae}'
                    ),
                )

    # Atualizar campos simples
    update_data = ordem_data.model_dump(exclude_unset=True)

    # Se um número foi gerado automaticamente, remover 'numero' de update_data
    # para evitar sobrescrever o valor gerado
    if (
        ordem_data.status == 'aprovada'
        and ordem.status == 'rascunho'
        and ordem.numero != 'auto'  # Número foi gerado (linha 453)
        and 'numero' in update_data
    ):
        del update_data['numero']

    # Tratar campos especiais
    if 'campos_especiais' in update_data:
        ordem.campos_especiais = (
            [ce.model_dump() for ce in ordem_data.campos_especiais]
            if ordem_data.campos_especiais
            else []
        )
        del update_data['campos_especiais']

    # Atualizar etapas se fornecidas
    if 'etapas' in update_data:
        # Atualizar data_saida
        if ordem_data.etapas:
            ordem.data_saida = min(e.dt_dep for e in ordem_data.etapas).date()
        else:
            ordem.data_saida = None

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

    # Atualizar tripulação se fornecida (batch query para evitar N+1)
    if 'tripulacao' in update_data:
        # Remover tripulação existente
        for trip in ordem.tripulacao:
            await session.delete(trip)

        # Criar nova tripulação
        if ordem_data.tripulacao:
            await _criar_tripulacao_batch(
                session, ordem.id, ordem_data.tripulacao
            )

        del update_data['tripulacao']

    # Atualizar etiquetas se fornecidas
    if 'etiquetas_ids' in update_data:
        if ordem_data.etiquetas_ids is not None:
            etiquetas_result = await session.execute(
                select(Etiqueta).where(
                    Etiqueta.id.in_(ordem_data.etiquetas_ids)
                )
            )
            ordem.etiquetas = list(etiquetas_result.scalars().all())
        else:
            ordem.etiquetas = []
        del update_data['etiquetas_ids']

    # Atualizar demais campos
    for key, value in update_data.items():
        if value is not None:
            setattr(ordem, key, value)

    await session.commit()

    # Buscar ordem com relacionamentos carregados para retorno
    ordem_loaded = await get_ordem_with_relations(session, ordem.id)

    return build_ordem_response(ordem_loaded)


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


# =============================================================================
# Rotas de Etiquetas (CRUD)
# =============================================================================


@router.get('/etiquetas/', response_model=list[EtiquetaSchema])
async def list_etiquetas(session: Session):
    """Lista todas as etiquetas cadastradas"""
    result = await session.execute(select(Etiqueta).order_by(Etiqueta.nome))
    return result.scalars().all()


@router.post(
    '/etiquetas/',
    response_model=EtiquetaSchema,
    status_code=HTTPStatus.CREATED,
)
async def create_etiqueta(
    etiqueta_data: EtiquetaCreate, session: Session, current_user: CurrentUser
):
    """Cria uma nova etiqueta"""
    etiqueta = Etiqueta(
        nome=etiqueta_data.nome,
        cor=etiqueta_data.cor,
        descricao=etiqueta_data.descricao,
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)
    return etiqueta


@router.put('/etiquetas/{id}', response_model=EtiquetaSchema)
async def update_etiqueta(
    id: int,
    etiqueta_data: EtiquetaUpdate,
    session: Session,
    current_user: CurrentUser,
):
    """Atualiza uma etiqueta existente"""
    etiqueta = await session.get(Etiqueta, id)
    if not etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Etiqueta não encontrada'
        )

    update_data = etiqueta_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(etiqueta, key, value)

    await session.commit()
    await session.refresh(etiqueta)
    return etiqueta


@router.delete('/etiquetas/{id}', status_code=HTTPStatus.OK)
async def delete_etiqueta(
    id: int, session: Session, current_user: CurrentUser
):
    """Remove uma etiqueta"""
    etiqueta = await session.get(Etiqueta, id)
    if not etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Etiqueta não encontrada'
        )

    await session.delete(etiqueta)
    await session.commit()
    return {'detail': 'Etiqueta removida com sucesso'}
