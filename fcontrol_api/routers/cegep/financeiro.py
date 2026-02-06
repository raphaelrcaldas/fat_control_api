from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.cegep.missoes import FragMisSchema, UserFragMis
from fcontrol_api.schemas.response import ApiPaginatedResponse
from fcontrol_api.utils.financeiro import custo_missao
from fcontrol_api.utils.responses import paginated_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/financeiro', tags=['CEGEP'])


@router.get('/pgts', response_model=ApiPaginatedResponse[dict])
async def get_pgto(
    session: Session,
    tipo_doc: list[str] = Query(None, description='Tipos de documento'),
    n_doc: int = None,
    sit: list[str] = Query(None, description='Situações'),
    user: str = None,
    user_id: int = None,
    tipo: list[str] = Query(None, description='Tipos de missão'),
    ini: date = None,
    fim: date = None,
    page: int = Query(1, ge=1, description='Número da página'),
    limit: int = Query(20, ge=1, le=100, description='Itens por página'),
):
    # Query base com joins
    base_query = (
        select(UserFrag, FragMis)
        .join(FragMis, (FragMis.id == UserFrag.frag_id))
        .join(User, (User.id == UserFrag.user_id))
    )

    # Query para contagem
    count_query = (
        select(func.count())
        .select_from(UserFrag)
        .join(FragMis, (FragMis.id == UserFrag.frag_id))
        .join(User, (User.id == UserFrag.user_id))
    )

    # Aplicar filtros em ambas as queries
    if tipo_doc:
        base_query = base_query.where(FragMis.tipo_doc.in_(tipo_doc))
        count_query = count_query.where(FragMis.tipo_doc.in_(tipo_doc))

    if n_doc:
        base_query = base_query.where(FragMis.n_doc == n_doc)
        count_query = count_query.where(FragMis.n_doc == n_doc)

    if sit:
        base_query = base_query.where(UserFrag.sit.in_(sit))
        count_query = count_query.where(UserFrag.sit.in_(sit))

    if user_id:
        base_query = base_query.where(UserFrag.user_id == user_id)
        count_query = count_query.where(UserFrag.user_id == user_id)

    if user:
        user_filter = User.nome_guerra.ilike(
            f'%{user}%'
        ) | User.nome_completo.ilike(f'%{user}%')
        base_query = base_query.where(user_filter)
        count_query = count_query.where(user_filter)

    if tipo:
        base_query = base_query.where(FragMis.tipo.in_(tipo))
        count_query = count_query.where(FragMis.tipo.in_(tipo))

    if ini:
        ini = datetime.combine(ini, time(0, 0, 0))
        base_query = base_query.where(FragMis.afast >= ini)
        count_query = count_query.where(FragMis.afast >= ini)

    if fim:
        fim = datetime.combine(fim, time(23, 59, 59))
        base_query = base_query.where(FragMis.afast <= fim)
        count_query = count_query.where(FragMis.afast <= fim)

    # Executar contagem total
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Aplicar ordenação e paginação
    # Ordenação determinística: afast > frag_id > user_frag_id
    # Garante consistência na paginação quando múltiplos usuários
    # estão na mesma missão (mesmo afast)
    offset = (page - 1) * limit
    stmt = (
        base_query
        .order_by(
            FragMis.afast.desc(),
            FragMis.id.desc(),
            UserFrag.id,
        )
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(stmt)
    result: list[tuple[UserFrag, FragMis]] = result.all()

    items = []
    for usr_frg, missao in result:
        uf_data = UserFragMis.model_validate(usr_frg).model_dump(
            exclude={'user_id', 'frag_id'}
        )
        mis = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )
        # Read costs from JSONB column (pre-calculated)
        # Usa valores diretamente do modelo SQLAlchemy para consistência
        # com o endpoint de comiss (evita problemas com enum serialization)
        mis = custo_missao(
            usr_frg.p_g,
            usr_frg.sit,
            mis,
        )

        items.append({
            'user_mis': uf_data,
            'missao': mis,
        })

    return paginated_response(
        items=items,
        total=total,
        page=page,
        per_page=limit,
    )
