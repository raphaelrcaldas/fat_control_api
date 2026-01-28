"""Router para Ordem de Missão (OM)"""

from datetime import date, datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.om import (
    Etiqueta,
    OrdemEtapa,
    OrdemMissao,
    OrdemTripulacao,
)
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.etiquetas import (
    EtiquetaCreate,
    EtiquetaSchema,
    EtiquetaUpdate,
)
from fcontrol_api.schemas.om import (
    ICAO_CODE_LENGTH,
    OrdemMissaoCreate,
    OrdemMissaoList,
    OrdemMissaoOut,
    OrdemMissaoUpdate,
    RouteSuggestionOut,
)
from fcontrol_api.schemas.pagination import PaginatedResponse
from fcontrol_api.security import get_current_user
from fcontrol_api.services.om import criar_tripulacao_batch
from fcontrol_api.utils.strings import escape_like

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
    status_ne: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    busca: str | None = None,
    etiquetas_ids: Annotated[list[int] | None, Query()] = None,
):
    """
    Lista ordens de missão com filtros e paginação.

    - **status**: Lista de status para incluir
    - **status_ne**: Status para excluir (not equal, ex: rascunho)
    - **data_inicio/data_fim**: Filtro por data de decolagem da primeira etapa
    - **busca**: Busca por número, localidade, tipo ou nome de guerra
    """
    # Query base: apenas ordens não deletadas
    query = select(OrdemMissao).where(OrdemMissao.deleted_at.is_(None))

    # Filtro por status (inclusão ou exclusão)
    if status:
        query = query.where(OrdemMissao.status.in_(status))
    elif status_ne:
        query = query.where(OrdemMissao.status != status_ne)

    # Filtro por busca (número, ICAO, tipo, ou nome de guerra)
    if busca:
        escaped_busca = escape_like(busca)
        escaped_busca_upper = escape_like(busca.upper())

        # Subquery: ordens com etapas que têm o código ICAO
        busca_pattern = f'%{escaped_busca_upper}%'
        etapas_subquery = (
            select(OrdemEtapa.ordem_id)
            .where(
                (OrdemEtapa.origem.ilike(busca_pattern, escape='\\'))
                | (OrdemEtapa.dest.ilike(busca_pattern, escape='\\'))
            )
            .distinct()
        )

        # Subquery: ordens com tripulantes que têm o nome de guerra
        tripulacao_subquery = (
            select(OrdemTripulacao.ordem_id)
            .join(OrdemTripulacao.tripulante)
            .join(Tripulante.user)
            .where(User.nome_guerra.ilike(f'%{escaped_busca}%', escape='\\'))
            .distinct()
        )

        query = query.where(
            (OrdemMissao.numero.ilike(f'%{escaped_busca}%', escape='\\'))
            | (OrdemMissao.id.in_(etapas_subquery))
            | (OrdemMissao.tipo.ilike(f'%{escaped_busca}%', escape='\\'))
            | (OrdemMissao.id.in_(tripulacao_subquery))
        )

    # Filtro por data (usa data_saida que é a data da primeira etapa)
    if data_inicio:
        query = query.where(OrdemMissao.data_saida >= data_inicio)
    if data_fim:
        query = query.where(OrdemMissao.data_saida <= data_fim)

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
        query
        .order_by(OrdemMissao.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(
            selectinload(OrdemMissao.etapas),
            selectinload(OrdemMissao.etiquetas),
        )
    )

    result = await session.scalars(query)
    ordens = result.all()

    # Transformar para OrdemMissaoList usando from_attributes do Pydantic
    items = [OrdemMissaoList.model_validate(ordem) for ordem in ordens]

    pages = (total + per_page - 1) // per_page if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get(
    '/route-suggestions',
    status_code=HTTPStatus.OK,
    response_model=RouteSuggestionOut | None,
)
async def get_route_suggestion(
    origem: str,
    dest: str,
    session: Session,
    current_user: CurrentUser,
):
    """
    Busca sugestão de rota baseada em missões anteriores (não rascunho).

    Realiza duas buscas:
    1. Rota completa (origem + dest): tvoo_etp, qtd_comb
    2. Apenas destino: alternativa, tvoo_alt

    Isso permite sugerir alternativa mesmo para rotas nunca voadas,
    desde que o destino já tenha sido visitado anteriormente.
    """
    # Validar códigos ICAO
    if len(origem) != ICAO_CODE_LENGTH or len(dest) != ICAO_CODE_LENGTH:
        return None

    origem_upper = origem.upper()
    dest_upper = dest.upper()

    # Filtro comum: ordens não-rascunho e não-deletadas
    base_filter = [
        OrdemMissao.status != 'rascunho',
        OrdemMissao.deleted_at.is_(None),
    ]

    # Query 1: Buscar rota completa (origem + dest) -> tvoo_etp, qtd_comb
    route_result = await session.execute(
        select(
            OrdemEtapa.tvoo_etp,
            OrdemEtapa.qtd_comb,
        )
        .join(OrdemMissao, OrdemEtapa.ordem_id == OrdemMissao.id)
        .where(
            OrdemEtapa.origem == origem_upper,
            OrdemEtapa.dest == dest_upper,
            *base_filter,
        )
        .order_by(OrdemMissao.created_at.desc(), OrdemMissao.id.desc())
        .limit(1)
    )
    route_row = route_result.first()

    # Query 2: Buscar dados do destino (apenas dest) -> alternativa, tvoo_alt
    dest_result = await session.execute(
        select(
            OrdemEtapa.alternativa,
            OrdemEtapa.tvoo_alt,
        )
        .join(OrdemMissao, OrdemEtapa.ordem_id == OrdemMissao.id)
        .where(
            OrdemEtapa.dest == dest_upper,
            *base_filter,
        )
        .order_by(OrdemMissao.created_at.desc(), OrdemMissao.id.desc())
        .limit(1)
    )
    dest_row = dest_result.first()

    # Nenhum dado encontrado
    if not route_row and not dest_row:
        return None

    # Construir resposta combinada
    return RouteSuggestionOut(
        dest=dest_upper,
        # Dados do destino
        alternativa=dest_row.alternativa if dest_row else None,
        tvoo_alt=dest_row.tvoo_alt if dest_row else None,
        # Dados da rota completa
        origem=origem_upper if route_row else None,
        tvoo_etp=route_row.tvoo_etp if route_row else None,
        qtd_comb=route_row.qtd_comb if route_row else None,
        # Flags
        has_route_data=route_row is not None,
        has_destination_data=dest_row is not None,
    )


@router.get('/{id}', status_code=HTTPStatus.OK, response_model=OrdemMissaoOut)
async def get_ordem(id: int, session: Session):
    """Busca uma ordem de missão por ID"""
    ordem = await session.scalar(
        select(OrdemMissao)
        .where(OrdemMissao.id == id, OrdemMissao.deleted_at.is_(None))
        .options(
            selectinload(OrdemMissao.tripulacao).selectinload(
                OrdemTripulacao.tripulante
            )
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
        etapa = OrdemEtapa(
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
        await criar_tripulacao_batch(session, ordem.id, ordem_data.tripulacao)

    # Vincular etiquetas
    if ordem_data.etiquetas_ids:
        etiquetas_result = await session.execute(
            select(Etiqueta).where(Etiqueta.id.in_(ordem_data.etiquetas_ids))
        )
        ordem.etiquetas = list(etiquetas_result.scalars().all())

    await session.commit()

    # Recarregar a ordem com todos os relacionamentos (incluindo aninhados)
    ordem_criada = await session.scalar(
        select(OrdemMissao)
        .where(OrdemMissao.id == ordem.id)
        .options(
            selectinload(OrdemMissao.tripulacao).selectinload(
                OrdemTripulacao.tripulante
            )
        )
    )

    return OrdemMissaoOut.model_validate(ordem_criada, from_attributes=True)


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

    # Validação de edição manual de número (somente para ordens aprovadas)
    if ordem_data.numero and ordem_data.numero != ordem.numero:
        # Só permite editar número em ordens aprovadas
        # (em rascunho, o número é gerado automaticamente na aprovação)
        status_atual = ordem_data.status or ordem.status
        if status_atual != 'aprovada':
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'O número da OM só pode ser editado '
                    'após a ordem ser aprovada'
                ),
            )

        # Validar unicidade do novo número (ano + UAE)
        target_year = None
        target_uae = ordem_data.uae or ordem.uae
        if ordem_data.etapas:
            target_year = min(e.dt_dep for e in ordem_data.etapas).year
        elif ordem.data_saida:
            target_year = ordem.data_saida.year

        if target_year and target_uae:
            existing = await session.scalar(
                select(OrdemMissao).where(
                    OrdemMissao.numero == ordem_data.numero,
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
                        f'Já existe uma ordem com o número '
                        f'{ordem_data.numero} no ano {target_year} '
                        f'para a UAE {target_uae}'
                    ),
                )

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
            etapa = OrdemEtapa(
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
            await criar_tripulacao_batch(
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

    # Recarregar a ordem com todos os relacionamentos (incluindo aninhados)
    ordem_atualizada = await session.scalar(
        select(OrdemMissao)
        .where(OrdemMissao.id == id)
        .options(
            selectinload(OrdemMissao.tripulacao).selectinload(
                OrdemTripulacao.tripulante
            )
        )
    )

    return OrdemMissaoOut.model_validate(
        ordem_atualizada, from_attributes=True
    )


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
