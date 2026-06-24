import json
from datetime import date, datetime, time, timedelta
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import (
    Etiqueta,
    FragEtiqueta,
    FragMis,
    PernoiteFrag,
    UserFrag,
)
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.estados_cidades import Cidade
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.missoes import (
    CidadePernoiteSchema,
    FragMisSchema,
    MissaoDetail,
    MissaoLogOut,
    MissoesFilterParams,
    PernoiteFragMis,
    UserFragMis,
)
from fcontrol_api.schemas.etiquetas import EtiquetaInput, EtiquetaSchema
from fcontrol_api.schemas.response import (
    ApiPaginatedResponse,
    ApiResponse,
)
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.security import ActiveOrg, get_current_user
from fcontrol_api.services.comis import (
    recalcular_comiss_afetados,
    verificar_usrs_comiss,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.missao import (
    adicionar_missao,
    sincronizar_custos_missao,
    verificar_conflitos,
    verificar_integridade_missao,
)
from fcontrol_api.utils.responses import paginated_response, success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/missoes', tags=['CEGEP'])

RESOURCE = 'missao'


def _missao_to_dict(m: FragMis) -> dict:
    """Snapshot JSON-serializável para auditoria (before/after).

    Acessa apenas atributos escalares para evitar lazy-load assíncrono
    de relacionamentos (pernoites/users/etiquetas) fora do greenlet.
    """
    return {
        'n_doc': m.n_doc,
        'tipo_doc': m.tipo_doc,
        'indenizavel': m.indenizavel,
        'acrec_desloc': m.acrec_desloc,
        'afast': m.afast.isoformat() if m.afast else None,
        'regres': m.regres.isoformat() if m.regres else None,
        'desc': m.desc,
        'obs': m.obs,
        'tipo': m.tipo,
    }


@router.get('/', response_model=ApiPaginatedResponse[FragMisSchema])
async def get_fragmentos(
    session: Session,
    active_org: ActiveOrg,
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
    - ini/fim: Janela de datas (sobreposição: inclui missões cujo
      intervalo afast-regres intersecta [ini, fim])
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

    # Query base com ordenação determinística (afast + id).
    # Filtro de datas por SOBREPOSIÇÃO: inclui toda missão cujo intervalo
    # [afast, regres] intersecta a janela [ini, fim]. Assim missões em
    # andamento ou que cruzam a borda da janela continuam visíveis.
    base_query = (
        select(FragMis)
        .options(selectinload(FragMis.users))
        .filter(
            FragMis.uae == active_org,
            FragMis.afast <= fim,
            FragMis.regres >= ini,
        )
        .order_by(FragMis.afast.desc(), FragMis.id.desc())
    )

    # Query de contagem. Usa COUNT(DISTINCT id) porque os filtros de
    # cidade/militar/etiqueta abaixo adicionam JOINs que multiplicam linhas;
    # sem o distinct o total ficaria inflado e quebraria a paginação.
    count_query = (
        select(func.count(FragMis.id.distinct()))
        .select_from(FragMis)
        .filter(
            FragMis.uae == active_org,
            FragMis.afast <= fim,
            FragMis.regres >= ini,
        )
    )

    # Aplica filtros validados em ambas as queries.
    # tipo_doc e tipo aceitam múltiplos valores separados por vírgula
    # (multi-select do front), portanto usamos IN ao invés de igualdade.
    if params.tipo_doc:
        tipos_doc = [
            t.strip() for t in params.tipo_doc.split(',') if t.strip()
        ]
        if tipos_doc:
            base_query = base_query.where(FragMis.tipo_doc.in_(tipos_doc))
            count_query = count_query.where(FragMis.tipo_doc.in_(tipos_doc))

    if params.n_doc:
        base_query = base_query.where(FragMis.n_doc == params.n_doc)
        count_query = count_query.where(FragMis.n_doc == params.n_doc)

    if params.tipo:
        tipos = [t.strip() for t in params.tipo.split(',') if t.strip()]
        if tipos:
            base_query = base_query.where(FragMis.tipo.in_(tipos))
            count_query = count_query.where(FragMis.tipo.in_(tipos))

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
    if params.etiqueta_ids:
        ids = [
            int(id.strip())
            for id in params.etiqueta_ids.split(',')
            if id.strip().isdigit()
        ]

        if ids:
            base_query = base_query.join(
                FragEtiqueta, FragEtiqueta.frag_id == FragMis.id
            ).where(FragEtiqueta.etiqueta_id.in_(ids))

            count_query = count_query.join(
                FragEtiqueta, FragEtiqueta.frag_id == FragMis.id
            ).where(FragEtiqueta.etiqueta_id.in_(ids))

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


# ============ ENDPOINTS DE ETIQUETAS ============


@router.get('/etiquetas', response_model=ApiResponse[list[EtiquetaSchema]])
async def get_etiquetas(session: Session, active_org: ActiveOrg):
    """Lista as etiquetas da org ativa"""
    stmt = (
        select(Etiqueta)
        .where(Etiqueta.uae == active_org)
        .order_by(Etiqueta.nome)
    )
    db_etiquetas = (await session.scalars(stmt)).all()
    return success_response(data=list(db_etiquetas))


@router.post('/etiquetas', response_model=ApiResponse[EtiquetaSchema])
async def create_or_update_etiqueta(
    payload: EtiquetaInput, session: Session, active_org: ActiveOrg
):
    """Cria ou atualiza uma etiqueta"""
    if payload.id:
        # Atualização (escopada: etiqueta de outra org -> 404)
        db_etiqueta = await session.scalar(
            select(Etiqueta).where(
                Etiqueta.id == payload.id, Etiqueta.uae == active_org
            )
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
            uae=active_org,
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
async def delete_etiqueta(
    etiqueta_id: int, session: Session, active_org: ActiveOrg
):
    """Remove uma etiqueta"""
    db_etiqueta = await session.scalar(
        select(Etiqueta).where(
            Etiqueta.id == etiqueta_id, Etiqueta.uae == active_org
        )
    )
    if not db_etiqueta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Etiqueta não encontrada',
        )

    await session.delete(db_etiqueta)
    await session.commit()

    return success_response(message='Etiqueta removida com sucesso')


@router.get(
    '/pernoites/cidades',
    response_model=ApiResponse[list[CidadePernoiteSchema]],
)
async def buscar_cidades_pernoite(
    session: Session,
    active_org: ActiveOrg,
    search: Annotated[str, Query()] = '',
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    dias: Annotated[int, Query(ge=1, le=3650)] = 180,
):
    """Busca cidades para pernoites com ranking por uso recente.

    As cidades mais usadas em pernoites da org ativa (janela dos últimos
    `dias`, por `data_ini`) vêm no topo e marcadas com `mais_usada`. Usa
    OUTER JOIN para preservar cidades nunca usadas (`usos=0`) como opção.
    """
    # Só vira "mais usada" (destaque) acima deste número de usos na janela.
    min_usos_destaque = 3

    corte = date.today() - timedelta(days=dias)

    usos_sub = (
        select(
            PernoiteFrag.cidade_id.label('cidade_id'),
            func.count(PernoiteFrag.id).label('usos'),
        )
        .join(FragMis, FragMis.id == PernoiteFrag.frag_id)
        .where(
            FragMis.uae == active_org,
            PernoiteFrag.data_ini >= corte,
        )
        .group_by(PernoiteFrag.cidade_id)
        .subquery()
    )

    usos = func.coalesce(usos_sub.c.usos, 0).label('usos')

    stmt = (
        select(Cidade, usos)
        .outerjoin(usos_sub, usos_sub.c.cidade_id == Cidade.codigo)
        .order_by(usos.desc(), Cidade.nome.asc(), Cidade.codigo)
        .limit(limit)
    )

    termo = search.strip()
    if termo:
        stmt = stmt.where(Cidade.nome.ilike(f'%{termo}%'))

    rows = (await session.execute(stmt)).all()

    data = [
        CidadePernoiteSchema(
            codigo=cidade.codigo,
            nome=cidade.nome,
            uf=cidade.uf,
            usos=total,
            mais_usada=total > min_usos_destaque,
        )
        for cidade, total in rows
    ]

    return success_response(data=data)


@router.get('/{id}', response_model=ApiResponse[MissaoDetail])
async def get_missao(id: int, session: Session, active_org: ActiveOrg):
    """Obter uma missão específica pelo ID, com histórico de auditoria."""
    missao = await session.scalar(
        select(FragMis)
        .options(selectinload(FragMis.users))
        .where(FragMis.id == id, FragMis.uae == active_org)
    )
    if not missao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada',
        )

    # Ordena usuários por posto/antiguidade
    missao.users.sort(
        key=lambda u: (
            u.user.posto.ant,
            u.user.ult_promo or date.min,
            u.user.ant_rel or 0,
        )
    )

    # Buscar logs de auditoria
    logs_result = await session.scalars(
        select(UserActionLog)
        .options(selectinload(UserActionLog.user))
        .where(
            UserActionLog.resource == RESOURCE,
            UserActionLog.resource_id == id,
        )
        .order_by(UserActionLog.timestamp.desc(), UserActionLog.id.desc())
        .limit(100)
    )

    logs = []
    for log in logs_result.all():
        try:
            before = json.loads(log.before) if log.before else None
        except (json.JSONDecodeError, TypeError):
            before = None
        try:
            after = json.loads(log.after) if log.after else None
        except (json.JSONDecodeError, TypeError):
            after = None
        logs.append(
            MissaoLogOut(
                id=log.id,
                user=UserPublic.model_validate(log.user),
                action=log.action,
                before=before,
                after=after,
                timestamp=log.timestamp,
            )
        )

    missao_detail = MissaoDetail.model_validate(missao)
    missao_detail.logs = logs
    # Verificação de integridade ao abrir a missão: compara o hash dos
    # inputs atuais com o gravado no cache de custos (detecta drift).
    missao_detail.custo_inconsistente = not verificar_integridade_missao(
        missao
    )

    return success_response(data=missao_detail)


@router.post('/', response_model=ApiResponse[None])
async def create_or_update_missao(
    payload: FragMisSchema,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
):
    # Capturar snapshot anterior e usuários antigos ANTES de deletar
    usuarios_antigos_comiss: list[tuple[int, date, date]] = []
    before_snapshot: dict | None = None
    if payload.id:
        missao_antiga = await session.scalar(
            select(FragMis)
            .options(selectinload(FragMis.users))
            .where(FragMis.id == payload.id, FragMis.uae == active_org)
        )
        if missao_antiga:
            before_snapshot = _missao_to_dict(missao_antiga)
            usuarios_antigos_comiss = [
                (
                    u.user_id,
                    missao_antiga.afast.date(),
                    missao_antiga.regres.date(),
                )
                for u in missao_antiga.users
                if u.sit == 'c'
            ]

    missao = await adicionar_missao(payload, session, active_org)

    await verificar_conflitos(payload, session)

    await verificar_usrs_comiss(
        [u for u in payload.users if u.sit == 'c'],
        payload.afast,
        payload.regres,
        session,
        active_org,
    )

    # Adiciona pernoites (flush para obter os IDs usados no cálculo)
    pernoites: list[PernoiteFrag] = []
    for p in payload.pernoites:
        pnt_data = PernoiteFragMis.model_validate(p).model_dump(
            exclude={'cidade', 'id', 'frag_id'}
        )
        pernoite = PernoiteFrag(**pnt_data, frag_id=missao.id)
        session.add(pernoite)
        await session.flush()
        pernoites.append(pernoite)

    # Adiciona militares
    users_frag: list[UserFrag] = []
    for u in payload.users:
        user_data = UserFragMis.model_validate(u).model_dump(
            exclude={'user', 'id', 'frag_id'}
        )
        user_frag = UserFrag(**user_data, frag_id=missao.id)
        session.add(user_frag)
        users_frag.append(user_frag)

    # Ponto único de invalidação: recalcula o cache de custos da missão e
    # dos comissionamentos afetados (situação nova + footprints antigos).
    await sincronizar_custos_missao(
        missao,
        users_frag,
        pernoites,
        session,
        active_org,
        footprints_antigos=tuple(usuarios_antigos_comiss),
    )

    # Log de auditoria
    after_snapshot = _missao_to_dict(missao)
    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='update' if payload.id else 'create',
        resource=RESOURCE,
        resource_id=missao.id,
        before=before_snapshot,
        after=after_snapshot,
    )

    await session.commit()

    return success_response(message='Missão salva com sucesso')


@router.delete('/{id}', response_model=ApiResponse[None])
async def delete_fragmis(
    id: int,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
):
    db_frag = await session.scalar(
        select(FragMis)
        .options(selectinload(FragMis.users))
        .where(FragMis.id == id, FragMis.uae == active_org)
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

    # Snapshot para auditoria antes de remover (acessa só escalares)
    before_snapshot = _missao_to_dict(db_frag)

    await session.execute(
        delete(PernoiteFrag).where(PernoiteFrag.frag_id == id)
    )
    await session.execute(delete(UserFrag).where(UserFrag.frag_id == id))

    await session.delete(db_frag)

    # Registra a exclusão. Os logs anteriores da missão são preservados
    # para manter a trilha de auditoria mesmo após a remoção.
    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='delete',
        resource=RESOURCE,
        resource_id=id,
        before=before_snapshot,
        after=None,
    )

    # Recalcular cache dos comissionamentos afetados após deletar
    for user_id, afast, regres in comiss_users:
        await recalcular_comiss_afetados(
            user_id, afast, regres, session, active_org
        )

    await session.commit()

    return success_response(message='Missão removida com sucesso')
