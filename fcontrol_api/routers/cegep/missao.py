from datetime import date, datetime, time
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import (
    Etiqueta,
    FragEtiqueta,
    FragMis,
    PernoiteFrag,
    UserFrag,
)
from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.schemas.etiquetas import EtiquetaInput, EtiquetaSchema
from fcontrol_api.schemas.missoes import (
    FragMisSchema,
    MissoesFilterParams,
    PernoiteFragMis,
    UserFragMis,
)
from fcontrol_api.schemas.response import (
    ApiPaginatedResponse,
    ApiResponse,
)
from fcontrol_api.services.comis import (
    recalcular_comiss_afetados,
    verificar_usrs_comiss,
)
from fcontrol_api.services.financeiro import cache_diarias, cache_soldos
from fcontrol_api.services.missao import adicionar_missao, verificar_conflitos
from fcontrol_api.utils.financeiro import calcular_custos_frag_mis
from fcontrol_api.utils.responses import paginated_response, success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/missoes', tags=['CEGEP'])


@router.get('/', response_model=ApiPaginatedResponse[FragMisSchema])
async def get_fragmentos(
    session: Session,
    params: MissoesFilterParams = Depends(),
):
    """
    Listar missões com filtros avançados e paginação.

    **Segurança:**
    - Todos os parâmetros são validados via Pydantic (MissoesFilterParams)
    - SQLAlchemy ORM usa parameterização automática para prevenir SQL injection
    - Limite máximo de 100 itens por página para prevenir DoS
    - Validação de tipos e limites de tamanho para todos os inputs

    **Filtros disponíveis:**
    - tipo_doc: Tipo do documento
    - n_doc: Número do documento
    - tipo: Tipo da missão
    - user_search: Nome de guerra (busca parcial case-insensitive)
    - city: Nome da cidade (busca parcial case-insensitive)
    - ini/fim: Intervalo de datas (afastamento/regresso)
    - etiqueta_ids: IDs de etiquetas separados por vírgula

    **Paginação:**
    - page: Número da página (padrão: 1)
    - per_page: Itens por página (padrão: 20, máx: 100)
    """
    # Pydantic já valida per_page <= 100,
    # mas garantimos via min() por defesa em profundidade
    per_page = min(params.per_page, 100)
    page = max(params.page, 1)  # Redundante, mas mantemos por segurança
    offset = (page - 1) * per_page

    # Conversão de datas com null checks
    # Se ini ou fim não foram fornecidos, usa valores padrão
    # que capturam todas as missões
    if params.ini:
        ini = datetime.combine(params.ini, time(0, 0, 0))
    else:
        # Data mínima que captura todas as missões
        ini = datetime(1900, 1, 1, 0, 0, 0)

    if params.fim:
        fim = datetime.combine(params.fim, time(23, 59, 59))
    else:
        # Data máxima que captura todas as missões
        fim = datetime(2100, 12, 31, 23, 59, 59)

    # Query base com ordenação determinística (afast + id)
    base_query = (
        select(FragMis)
        .options(selectinload(FragMis.users))
        .filter(FragMis.afast >= ini, FragMis.regres <= fim)
        .order_by(FragMis.afast.desc(), FragMis.id.desc())
    )

    # Query de contagem (sem options e sem ordenação para performance)
    count_query = (
        select(func.count())
        .select_from(FragMis)
        .filter(FragMis.afast >= ini, FragMis.regres <= fim)
    )

    # Aplica filtros validados em ambas as queries
    if params.tipo_doc:
        base_query = base_query.where(FragMis.tipo_doc == params.tipo_doc)
        count_query = count_query.where(FragMis.tipo_doc == params.tipo_doc)

    if params.n_doc:
        base_query = base_query.where(FragMis.n_doc == params.n_doc)
        count_query = count_query.where(FragMis.n_doc == params.n_doc)

    if params.tipo:
        base_query = base_query.where(FragMis.tipo == params.tipo)
        count_query = count_query.where(FragMis.tipo == params.tipo)

    # Filtro por cidade (busca parcial case-insensitive)
    # SQLAlchemy ORM usa parameterização automática, prevenindo SQL injection
    if params.city:
        base_query = (
            base_query
            .join(PernoiteFrag)
            .join(Cidade)
            .where(Cidade.nome.ilike(f'%{params.city}%'))
        )
        count_query = (
            count_query
            .join(PernoiteFrag)
            .join(Cidade)
            .where(Cidade.nome.ilike(f'%{params.city}%'))
        )

    # Filtro por nome de guerra (busca parcial case-insensitive)
    # SQLAlchemy ORM usa parameterização automática, prevenindo SQL injection
    if params.user_search:
        base_query = (
            base_query
            .join(UserFrag)
            .join(User)
            .where(User.nome_guerra.ilike(f'%{params.user_search}%'))
        )
        count_query = (
            count_query
            .join(UserFrag)
            .join(User)
            .where(User.nome_guerra.ilike(f'%{params.user_search}%'))
        )

    # Filtro por etiquetas (multi-select)
    # Parsing seguro com tratamento de erro e validação
    if params.etiqueta_ids:
        try:
            # Pydantic já validou o padrão regex,
            # mas fazemos parsing defensivo
            ids = [
                int(id.strip())
                for id in params.etiqueta_ids.split(',')
                if id.strip().isdigit()
            ]

            # Só aplica filtro se houver IDs válidos
            if ids:
                base_query = base_query.join(
                    FragEtiqueta, FragEtiqueta.frag_id == FragMis.id
                ).where(FragEtiqueta.etiqueta_id.in_(ids))

                count_query = count_query.join(
                    FragEtiqueta, FragEtiqueta.frag_id == FragMis.id
                ).where(FragEtiqueta.etiqueta_id.in_(ids))

        except (ValueError, AttributeError):
            # Se parsing falhar (não deveria devido validação Pydantic),
            # ignora filtro de etiquetas silenciosamente
            pass

    # Executa count e fetch
    total = await session.scalar(count_query) or 0
    frags_result = await session.scalars(
        base_query.offset(offset).limit(per_page)
    )
    db_frags = frags_result.unique().all()

    # Ordena os usuários dentro de cada missão por posto/antiguidade
    for frag in db_frags:
        frag.users.sort(
            key=lambda u: (
                u.user.posto.ant,
                u.user.ult_promo or date.min,
                u.user.ant_rel or 0,
            )
        )

    return paginated_response(
        items=db_frags,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post('/', response_model=ApiResponse[None])
async def create_or_update_missao(payload: FragMisSchema, session: Session):
    # Capturar usuários antigos ANTES de deletar (para recalcular removidos)
    usuarios_antigos_comiss: list[tuple[int, date, date]] = []
    if payload.id:
        missao_antiga = await session.scalar(
            select(FragMis)
            .options(selectinload(FragMis.users))
            .where(FragMis.id == payload.id)
        )
        if missao_antiga:
            usuarios_antigos_comiss = [
                (
                    u.user_id,
                    missao_antiga.afast.date(),
                    missao_antiga.regres.date(),
                )
                for u in missao_antiga.users
                if u.sit == 'c'
            ]

    missao = await adicionar_missao(payload, session)

    await verificar_conflitos(payload, session)

    await verificar_usrs_comiss(
        [u for u in payload.users if u.sit == 'c'],
        payload.afast,
        payload.regres,
        session,
    )

    # Adiciona pernoites e prepara inputs validados
    pernoites_input: list[CustoPernoiteInput] = []
    for p in payload.pernoites:
        pnt_data = PernoiteFragMis.model_validate(p).model_dump(
            exclude={'cidade', 'id', 'frag_id'}
        )
        pernoite = PernoiteFrag(**pnt_data, frag_id=missao.id)
        session.add(pernoite)
        await session.flush()  # Flush para obter o ID do pernoite

        # Criar input validado com Pydantic
        pernoite_input = CustoPernoiteInput(
            id=pernoite.id,
            data_ini=pernoite.data_ini,
            data_fim=pernoite.data_fim,
            meia_diaria=pernoite.meia_diaria,
            acrec_desloc=pernoite.acrec_desloc,
            cidade_codigo=p.cidade.codigo,  # Extrai código diretamente
        )
        pernoites_input.append(pernoite_input)

    # Adiciona militares e prepara inputs validados
    users_frag_input: list[CustoUserFragInput] = []
    for u in payload.users:
        user_data = UserFragMis.model_validate(u).model_dump(
            exclude={'user', 'id', 'frag_id'}
        )
        session.add(UserFrag(**user_data, frag_id=missao.id))

        # Criar input validado com Pydantic
        user_input = CustoUserFragInput(
            p_g=user_data['p_g'],
            sit=user_data['sit'],
        )
        users_frag_input.append(user_input)

    # Carregar caches necessários para cálculo de custos
    valores_cache = await cache_diarias(session)
    soldos_cache = await cache_soldos(session)

    # Carregar grupos_pg e grupos_cidade
    grupos_pg = dict(
        (await session.execute(select(GrupoPg.pg_short, GrupoPg.grupo))).all()
    )
    grupos_cidade = dict(
        (
            await session.execute(
                select(GrupoCidade.cidade_id, GrupoCidade.grupo)
            )
        ).all()
    )

    # Criar input validado da missão
    frag_mis_input = CustoFragMisInput(acrec_desloc=missao.acrec_desloc)

    # Calcular custos com inputs validados e tipados
    custos = calcular_custos_frag_mis(
        frag_mis_input,
        users_frag_input,
        pernoites_input,
        grupos_pg,
        grupos_cidade,
        valores_cache,
        soldos_cache,
    )

    # Atualizar campo custos na missão
    missao.custos = custos

    # Recalcular comissionamentos de todos os usuários envolvidos
    # (antigos removidos + novos/mantidos com sit='c')
    usuarios_envolvidos = {
        user_id for user_id, _, _ in usuarios_antigos_comiss
    }
    usuarios_envolvidos.update(
        u.user_id for u in payload.users if u.sit == 'c'
    )

    afast_date = (
        payload.afast.date()
        if hasattr(payload.afast, 'date')
        else payload.afast
    )
    regres_date = (
        payload.regres.date()
        if hasattr(payload.regres, 'date')
        else payload.regres
    )

    for user_id in usuarios_envolvidos:
        await recalcular_comiss_afetados(
            user_id, afast_date, regres_date, session
        )

    await session.commit()

    return success_response(message='Missão salva com sucesso')


@router.delete('/{id}', response_model=ApiResponse[None])
async def delete_fragmis(id: int, session: Session):
    db_frag = await session.scalar(
        select(FragMis)
        .options(selectinload(FragMis.users))
        .where((FragMis.id == id))
    )
    if not db_frag:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Missão não encontrada',
        )

    # Guardar dados antes de deletar para recalcular comissionamentos
    comiss_users = [
        (u.user_id, db_frag.afast.date(), db_frag.regres.date())
        for u in db_frag.users
        if u.sit == 'c'
    ]

    await session.execute(
        delete(PernoiteFrag).where(PernoiteFrag.frag_id == id)
    )
    await session.execute(delete(UserFrag).where(UserFrag.frag_id == id))

    await session.delete(db_frag)

    # Recalcular cache dos comissionamentos afetados após deletar
    for user_id, afast, regres in comiss_users:
        await recalcular_comiss_afetados(user_id, afast, regres, session)

    await session.commit()

    return success_response(message='Missão removida com sucesso')


# ============ ENDPOINTS DE ETIQUETAS ============


@router.get('/etiquetas', response_model=ApiResponse[list[EtiquetaSchema]])
async def get_etiquetas(session: Session):
    """Lista todas as etiquetas disponíveis"""
    stmt = select(Etiqueta).order_by(Etiqueta.nome)
    db_etiquetas = (await session.scalars(stmt)).all()
    return success_response(data=list(db_etiquetas))


@router.post('/etiquetas', response_model=ApiResponse[EtiquetaSchema])
async def create_or_update_etiqueta(payload: EtiquetaInput, session: Session):
    """Cria ou atualiza uma etiqueta"""
    if payload.id:
        # Atualização
        db_etiqueta = await session.scalar(
            select(Etiqueta).where(Etiqueta.id == payload.id)
        )
        if not db_etiqueta:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail='Etiqueta não encontrada',
            )
        db_etiqueta.nome = payload.nome
        db_etiqueta.cor = payload.cor
        db_etiqueta.descricao = payload.descricao
        msg = 'Etiqueta atualizada com sucesso'
    else:
        # Criação
        db_etiqueta = Etiqueta(
            nome=payload.nome,
            cor=payload.cor,
            descricao=payload.descricao,
        )
        session.add(db_etiqueta)
        msg = 'Etiqueta criada com sucesso'

    await session.commit()
    await session.refresh(db_etiqueta)

    return success_response(
        data=EtiquetaSchema.model_validate(db_etiqueta),
        message=msg,
    )


@router.delete('/etiquetas/{etiqueta_id}', response_model=ApiResponse[None])
async def delete_etiqueta(etiqueta_id: int, session: Session):
    """Remove uma etiqueta"""
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(Etiqueta.id == etiqueta_id)
    )
    if not db_etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etiqueta não encontrada',
        )

    await session.delete(db_etiqueta)
    await session.commit()

    return success_response(message='Etiqueta removida com sucesso')
