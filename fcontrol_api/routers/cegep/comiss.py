import json
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Boolean, and_, cast, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.models.cegep.orcamento import OrcamentoAnual
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.comiss import (
    ComissAbertura,
    ComissDeletePreview,
    ComissDetail,
    ComissFechamento,
    ComissLogOut,
    ComissMissaoPreview,
    ComissPublic,
    ComissSchema,
    ComissSummaryResponse,
    ComissSummaryTotal,
)
from fcontrol_api.schemas.cegep.missoes import FragMisEmbed, FragMisSchema
from fcontrol_api.schemas.response import ApiResponse, ResponseStatus
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.security import (
    ActiveOrg,
    ensure_org_permission_or_owner,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.comis import (
    filtro_missoes_periodo,
    recalcular_cache_comiss,
    validar_fechamento_comiss,
    verificar_conflito_comiss,
)
from fcontrol_api.services.custos import custo_missao
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.missao import verificar_integridade_missao
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/comiss', tags=['CEGEP'])

RESOURCE = 'comissionamento'

# Gating RBAC pelo recurso `comiss` (apoio_avancado tem CRUD; a leitura é
# concedida também a dout/ops). O escopo por org já é feito via active_org.
ViewComiss = Depends(permission_checker('comiss', 'view'))
CreateComiss = Depends(permission_checker('comiss', 'create'))
UpdateComiss = Depends(permission_checker('comiss', 'update'))
DeleteComiss = Depends(permission_checker('comiss', 'delete'))


def _comiss_to_dict(c: Comissionamento) -> dict:
    """Snapshot JSON-serializável para auditoria (before/after)."""
    return ComissSchema.model_validate(c).model_dump(
        mode='json', exclude={'id', 'user_id'}
    )


@router.get(
    '/',
    response_model=ApiResponse[list[ComissPublic]],
)
async def get_cmtos(
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
    user_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    pg: str | None = None,
    tipo: str | None = None,
    modulo: str | None = None,
):
    """
    Lista comissionamentos com valores pré-calculados do cache.
    Não retorna missões - use GET /{comiss_id} para detalhes.

    Filtros:
    - pg: postos/graduações separados por vírgula (ex: "cp,1t,2t")
    - tipo: "periodo" ou "comparativo"
    - modulo: "sim" ou "nao"
    """
    # Self-service: o tripulante lista os PRÓPRIOS comissionamentos
    # (user_id == ele) sem `comiss.view` — usado pelo portal FatBird.
    # Qualquer consulta mais ampla (outro user_id, ou sem filtro → owner_id
    # None) exige a permissão de role na org ativa.
    await ensure_org_permission_or_owner(
        current_user, session, active_org, 'comiss', 'view', user_id
    )

    query = (
        select(Comissionamento)
        .join(User)
        .where(Comissionamento.uae == active_org)
        .order_by(Comissionamento.data_ab.desc())
    )

    if user_id:
        query = query.where(Comissionamento.user_id == user_id)

    if status:
        query = query.where(Comissionamento.status == status)
        if status == 'fechado':
            query = query.limit(20)

    if search:
        query = query.where(
            User.nome_guerra.ilike(f'%{search}%')
            | User.nome_completo.ilike(f'%{search}%')
        )

    if pg:
        pg_list = [p.strip() for p in pg.split(',') if p.strip()]
        if pg_list:
            query = query.where(User.p_g.in_(pg_list))

    if tipo == 'periodo':
        query = query.where(Comissionamento.dias_cumprir.isnot(None))
    elif tipo == 'comparativo':
        query = query.where(Comissionamento.dias_cumprir.is_(None))

    if modulo == 'sim':
        query = query.where(
            cast(
                Comissionamento.cache_calc['modulo'].astext,
                Boolean,
            ).is_(True)
        )
    elif modulo == 'nao':
        query = query.where(
            cast(
                Comissionamento.cache_calc['modulo'].astext,
                Boolean,
            ).is_not(True)
        )

    result = await session.scalars(query)
    comiss_list = result.all()

    response = []
    for comiss in comiss_list:
        cache = comiss.cache_calc or {}
        base = ComissSchema.model_validate(comiss)
        response.append(
            ComissPublic(
                id=base.id,
                status=base.status,
                dep=base.dep,
                data_ab=base.data_ab,
                qtd_aj_ab=base.qtd_aj_ab,
                valor_aj_ab=base.valor_aj_ab,
                data_fc=base.data_fc,
                qtd_aj_fc=base.qtd_aj_fc,
                valor_aj_fc=base.valor_aj_fc,
                dias_cumprir=base.dias_cumprir,
                doc_prop=base.doc_prop,
                doc_aut=base.doc_aut,
                doc_enc=base.doc_enc,
                user=UserPublic.model_validate(comiss.user),
                dias_comp=cache.get('dias_comp', 0),
                diarias_comp=cache.get('diarias_comp', 0),
                vals_comp=cache.get('vals_comp', 0),
                modulo=cache.get('modulo', False),
                completude=cache.get('completude', 0),
                missoes_count=cache.get('missoes_count', 0),
            )
        )

    return success_response(data=response)


@router.get(
    '/summary',
    response_model=ApiResponse[ComissSummaryResponse],
    dependencies=[ViewComiss],
)
async def get_summary(
    session: Session,
    ano: int,
    active_org: ActiveOrg,
):
    """
    Retorna o summary orçamentário dos comissionamentos do ano escolhido.
    """
    query = (
        select(Comissionamento)
        .join(User)
        .where(
            Comissionamento.uae == active_org,
            (func.extract('year', Comissionamento.data_ab) == ano)
            | (func.extract('year', Comissionamento.data_fc) == ano),
        )
        .order_by(Comissionamento.data_ab.desc())
    )

    result = await session.scalars(query)
    comiss_list = result.all()

    orcamento = await session.scalar(
        select(OrcamentoAnual).where(OrcamentoAnual.ano_ref == ano)
    )

    orc_total = orcamento.total if orcamento else 0.0
    orc_abertura = orcamento.abertura if orcamento else 0.0
    orc_fechamento = orcamento.fechamento if orcamento else 0.0

    soma_ab = 0.0
    soma_fc = 0.0
    previsao_fc = 0.0

    response_comiss = []

    for comiss in comiss_list:
        if comiss.data_ab and comiss.data_ab.year == ano:
            soma_ab += comiss.valor_aj_ab or 0.0

        if comiss.data_fc and comiss.data_fc.year == ano:
            if comiss.status == 'fechado':
                soma_fc += comiss.valor_aj_fc or 0.0
            else:
                previsao_fc += comiss.valor_aj_fc or 0.0

        cache = comiss.cache_calc or {}
        base = ComissSchema.model_validate(comiss)
        response_comiss.append(
            ComissPublic(
                id=base.id,
                status=base.status,
                dep=base.dep,
                data_ab=base.data_ab,
                qtd_aj_ab=base.qtd_aj_ab,
                valor_aj_ab=base.valor_aj_ab,
                data_fc=base.data_fc,
                qtd_aj_fc=base.qtd_aj_fc,
                valor_aj_fc=base.valor_aj_fc,
                dias_cumprir=base.dias_cumprir,
                doc_prop=base.doc_prop,
                doc_aut=base.doc_aut,
                doc_enc=base.doc_enc,
                user=UserPublic.model_validate(comiss.user),
                completude=cache.get('completude', 0),
                modulo=cache.get('modulo', False),
            )
        )

    data = ComissSummaryResponse(
        orcamento_id=orcamento.id if orcamento else None,
        fechamento=ComissFechamento(
            soma=soma_fc,
            previsao=previsao_fc,
            orcamento=orc_fechamento,
        ),
        abertura=ComissAbertura(
            soma=soma_ab,
            orcamento=orc_abertura,
        ),
        total=ComissSummaryTotal(
            soma_abertura=soma_ab,
            soma_fechamento=soma_fc,
            soma=soma_ab + soma_fc,
            previsao=previsao_fc,
            orcamento=orc_total,
        ),
        comissionamentos=response_comiss,
    )

    return success_response(data=data)


@router.get(
    '/{comiss_id}',
    response_model=ApiResponse[ComissDetail],
)
async def get_cmto_by_id(
    comiss_id: int,
    session: Session,
    active_org: ActiveOrg,
    current_user: CurrentUser,
):
    """
    Retorna um comissionamento com todas as missões e o histórico de auditoria.
    """
    comiss = await session.scalar(
        select(Comissionamento).where(
            Comissionamento.id == comiss_id,
            Comissionamento.uae == active_org,
        )
    )

    if not comiss:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Comissionamento não encontrado',
        )

    # Self-service: o dono vê o próprio comissionamento (portal FatBird)
    # sem `comiss.view`; terceiros exigem a permissão de role na org ativa.
    await ensure_org_permission_or_owner(
        current_user, session, active_org, 'comiss', 'view', comiss.user_id
    )

    cache = comiss.cache_calc or {}
    base = ComissSchema.model_validate(comiss)

    missoes_query = (
        select(FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == comiss.user_id,
                UserFrag.sit == 'c',
                UserFrag.frag_id == FragMis.id,
            ),
        )
        # users carregados (selectin) para a verificação de integridade
        # por hash de cada missão na abertura do comissionamento
        .options(selectinload(FragMis.users))
        .where(
            filtro_missoes_periodo(
                comiss.uae, comiss.data_ab, comiss.data_fc
            )
        )
        .order_by(FragMis.afast)
    )

    result = await session.execute(missoes_query)
    registros = result.all()

    missoes = []
    for missao, user_frag in registros:
        mis_dict = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )
        mis_dict = custo_missao(user_frag.p_g, user_frag.sit, mis_dict)
        # Verificação por hash além da heurística de chave faltante: marca
        # drift do cache frente aos inputs atuais da missão.
        if not verificar_integridade_missao(missao):
            mis_dict['custo_inconsistente'] = True
        missoes.append(FragMisEmbed.model_validate(mis_dict))

    # Integridade dos agregados: o cache persistido (vals_comp/dias_comp/
    # diarias_comp/missoes_count) deve coincidir com a soma ao vivo das
    # missões recém-computadas. Divergência => cache obsoleto (ex.:
    # recálculo não disparado após mudança numa missão) ou alguma missão
    # com custo individual desatualizado. A verificação é do backend (dono
    # do cache); o frontend apenas exibe a flag resultante.
    vals_live = round(sum(m.valor_total for m in missoes), 2)
    dias_live = sum(m.dias for m in missoes)
    diarias_live = sum(m.diarias for m in missoes)

    cache_inconsistente = (
        any(m.custo_inconsistente for m in missoes)
        or cache.get('missoes_count', 0) != len(missoes)
        or dias_live != cache.get('dias_comp', 0)
        or abs(vals_live - cache.get('vals_comp', 0)) > 0.01
        or abs(diarias_live - cache.get('diarias_comp', 0)) > 0.01
    )

    logs_query = (
        select(UserActionLog)
        .options(selectinload(UserActionLog.user))
        .where(
            UserActionLog.resource == RESOURCE,
            UserActionLog.resource_id == comiss_id,
        )
        .order_by(UserActionLog.timestamp.desc(), UserActionLog.id.desc())
        .limit(100)
    )

    logs_result = await session.scalars(logs_query)
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
            ComissLogOut(
                id=log.id,
                user=UserPublic.model_validate(log.user),
                action=log.action,
                before=before,
                after=after,
                timestamp=log.timestamp,
            )
        )

    detail = ComissDetail(
        id=base.id,
        status=base.status,
        dep=base.dep,
        data_ab=base.data_ab,
        qtd_aj_ab=base.qtd_aj_ab,
        valor_aj_ab=base.valor_aj_ab,
        data_fc=base.data_fc,
        qtd_aj_fc=base.qtd_aj_fc,
        valor_aj_fc=base.valor_aj_fc,
        dias_cumprir=base.dias_cumprir,
        doc_prop=base.doc_prop,
        doc_aut=base.doc_aut,
        doc_enc=base.doc_enc,
        user=UserPublic.model_validate(comiss.user),
        dias_comp=cache.get('dias_comp', 0),
        diarias_comp=cache.get('diarias_comp', 0),
        vals_comp=cache.get('vals_comp', 0),
        modulo=cache.get('modulo', False),
        completude=cache.get('completude', 0),
        missoes_count=len(missoes),
        cache_inconsistente=cache_inconsistente,
        missoes=missoes,
        logs=logs,
    )

    return success_response(data=detail)


@router.post(
    '/',
    response_model=ApiResponse[None],
    dependencies=[CreateComiss],
)
async def create_cmto(
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    comiss: ComissSchema,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            (Comissionamento.user_id == comiss.user_id)
            & (Comissionamento.status == 'aberto')
            & (Comissionamento.uae == active_org)
        )
    )
    if db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Já existe um comissionamento aberto para este usuário.',
        )

    await verificar_conflito_comiss(
        comiss.user_id, comiss.data_ab, comiss.data_fc, session, active_org
    )

    comiss_data = ComissSchema.model_validate(comiss).model_dump(
        exclude={'id'}
    )
    new_comiss = Comissionamento(**comiss_data, uae=active_org)
    session.add(new_comiss)
    await session.flush()

    if new_comiss.status == 'fechado':
        await validar_fechamento_comiss(new_comiss, session)
    else:
        await recalcular_cache_comiss(new_comiss.id, session)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='create',
        resource=RESOURCE,
        resource_id=new_comiss.id,
        before=None,
        after=_comiss_to_dict(new_comiss),
    )

    await session.commit()

    return success_response(message='Comissionamento criado com sucesso')


@router.put(
    '/{comiss_id}',
    response_model=ApiResponse[None],
    dependencies=[UpdateComiss],
)
async def update_cmto(
    comiss_id: int,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    comiss: ComissSchema,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            Comissionamento.id == comiss_id,
            Comissionamento.uae == active_org,
        )
    )

    if not db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento não encontrado',
        )

    await verificar_conflito_comiss(
        comiss.user_id,
        comiss.data_ab,
        comiss.data_fc,
        session,
        active_org,
        comiss_id,
    )

    mis_comiss = await session.scalars(
        select(FragMis, Comissionamento)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == Comissionamento.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .join(
            FragMis,
            and_(
                FragMis.id == UserFrag.frag_id,
                filtro_missoes_periodo(
                    Comissionamento.uae,
                    Comissionamento.data_ab,
                    Comissionamento.data_fc,
                ),
            ),
        )
        .where(Comissionamento.id == comiss_id)
    )
    mis_comiss = mis_comiss.all()

    mis_update_comiss = await session.scalars(
        select(FragMis, Comissionamento)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == Comissionamento.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .join(
            FragMis,
            and_(
                FragMis.id == UserFrag.frag_id,
                filtro_missoes_periodo(
                    Comissionamento.uae, comiss.data_ab, comiss.data_fc
                ),
            ),
        )
        .where(Comissionamento.id == comiss_id)
    )
    mis_update_comiss = mis_update_comiss.all()

    mis_not_found: list[FragMis] = []
    for mis in mis_comiss:
        try:
            mis_update_comiss.index(mis)
        except ValueError:
            mis_not_found.append(mis)

    if mis_not_found:
        msg = '\nAs seguintes missões ficarão fora do escopo:\n'

        for mis in mis_not_found:
            msg += f'- {mis.tipo_doc} {mis.n_doc} {mis.afast}\n'.upper()

        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=msg,
        )

    before = _comiss_to_dict(db_comiss)

    for key, value in comiss.model_dump(exclude_unset=True).items():
        setattr(db_comiss, key, value)

    await session.flush()

    # Recalcula o cache (completude, etc.) para refletir mudanças em
    # dias_cumprir/datas. No fechamento, validar_fechamento_comiss já
    # recalcula antes de validar.
    if db_comiss.status == 'fechado':
        await validar_fechamento_comiss(db_comiss, session)
    else:
        await recalcular_cache_comiss(comiss_id, session)

    after = _comiss_to_dict(db_comiss)

    if before != after:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE,
            resource_id=comiss_id,
            before=before,
            after=after,
        )

    await session.commit()
    await session.refresh(db_comiss)

    return success_response(message='Comissionamento atualizado com sucesso')


@router.delete(
    '/{comiss_id}',
    response_model=ApiResponse[ComissDeletePreview | None],
    dependencies=[DeleteComiss],
)
async def delete_cmto(
    comiss_id: int,
    session: Session,
    active_org: ActiveOrg,
    confirm: bool = False,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            Comissionamento.id == comiss_id,
            Comissionamento.uae == active_org,
        )
    )

    if not db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Comissionamento não encontrado',
        )

    missoes_query = (
        select(FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.frag_id == FragMis.id,
                UserFrag.user_id == db_comiss.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .where(
            filtro_missoes_periodo(
                db_comiss.uae, db_comiss.data_ab, db_comiss.data_fc
            )
        )
        .order_by(FragMis.afast)
    )

    result = await session.execute(missoes_query)
    registros = result.all()

    # Sem missoes → deleta direto (+ limpa logs)
    if not registros:
        await session.execute(
            delete(UserActionLog).where(
                UserActionLog.resource == RESOURCE,
                UserActionLog.resource_id == comiss_id,
            )
        )
        await session.delete(db_comiss)
        await session.commit()
        return success_response(message='Comissionamento deletado com sucesso')

    # Com missoes, sem confirmacao → preview
    if not confirm:
        missoes_preview = [
            ComissMissaoPreview(
                id=missao.id,
                tipo_doc=missao.tipo_doc,
                n_doc=missao.n_doc,
                desc=missao.desc,
                afast=missao.afast,
                regres=missao.regres,
            )
            for missao, _ in registros
        ]

        return ApiResponse(
            status=ResponseStatus.WARNING,
            data=ComissDeletePreview(
                missoes_count=len(missoes_preview),
                missoes=missoes_preview,
            ),
            message=(
                f'Este comissionamento possui '
                f'{len(missoes_preview)} missão(ões) '
                f'vinculada(s). Confirme para prosseguir '
                f'com a exclusão.'
            ),
        )

    # Com confirmacao → cascade delete + limpa logs
    frag_ids = set()
    for missao, user_frag in registros:
        frag_ids.add(missao.id)
        await session.delete(user_frag)

    await session.flush()

    removed_count = len(frag_ids)
    orphan_count = 0

    for frag_id in frag_ids:
        remaining = await session.scalar(
            select(func.count(UserFrag.id)).where(
                UserFrag.frag_id == frag_id,
                UserFrag.sit == 'c',
            )
        )
        if remaining == 0:
            orphan_mission = await session.get(FragMis, frag_id)
            if orphan_mission:
                await session.delete(orphan_mission)
                orphan_count += 1

    await session.execute(
        delete(UserActionLog).where(
            UserActionLog.resource == RESOURCE,
            UserActionLog.resource_id == comiss_id,
        )
    )

    await session.delete(db_comiss)
    await session.commit()

    parts = ['Comissionamento deletado']
    if removed_count:
        parts.append(f'{removed_count} missão(ões) desvinculada(s)')
    if orphan_count:
        parts.append(f'{orphan_count} missão(ões) órfã(s) removida(s)')

    return success_response(message='. '.join(parts) + '.')
