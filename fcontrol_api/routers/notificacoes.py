"""Notificações in-app (client + FatBird).

Router self-service, SEM `permission_checker`: o sino existe para
qualquer autenticado e o tripulante do FatBird não tem role — um gate de
permissão trancaria o portal inteiro (mesmo racional de
`routers/feedbacks.py`). O escopo vem de dentro: toda query filtra pelo
próprio `user_id` (diretas) ou pelas permissões resolvidas na leitura
(tarefas), e o único guard é o `has_org_permission` dinâmico do
`/resolver` — argumentos vêm da linha, não de constantes, então nada
disso entra no catálogo `rbac-resources.json`.

Segregação por app imposta no backend: a audiência é derivada do
`app_client` do TOKEN (`request.state.app_client`, populado pelo
middleware) e filtra TODAS as queries e mutações — token do client não
vê nem marca lida notificação de tripulante, e vice-versa. É atributo do
token, não parâmetro do request: o front não escolhe o que vê.

Escopo de org (decisão consciente): usa `ActiveOrgOptional`, nunca
`ActiveOrg` — admin de sistema sem org ativa tem diretas e receberia 400.
Diretas ignoram a org ativa (dado da pessoa); tarefas filtram por
`uae == active_org`.
"""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.enums.notificacao import NotifEscopo
from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.notificacoes import (
    NotificacaoContador,
    NotificacaoOut,
)
from fcontrol_api.schemas.response import ApiPaginatedResponse, ApiResponse
from fcontrol_api.security import (
    ActiveOrgOptional,
    get_current_user,
    has_org_permission,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.notificacoes import (
    audiencia_do_app,
    condicoes_visiveis,
)
from fcontrol_api.utils.responses import paginated_response, success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_app_client(request: Request) -> str | None:
    """Cliente OAuth do token (populado pelo middleware de autenticação)."""
    return getattr(request.state, 'app_client', None)


AppClient = Annotated[str | None, Depends(get_app_client)]

router = APIRouter(prefix='/notificacoes', tags=['Notificações'])


@router.get('/', response_model=ApiPaginatedResponse[NotificacaoOut])
async def list_notificacoes(
    session: Session,
    user: CurrentUser,
    active_org: ActiveOrgOptional,
    app_client: AppClient,
    apenas_pendentes: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Lista única (diretas + tarefas visíveis), mais recentes primeiro."""
    visiveis = await condicoes_visiveis(session, user, active_org, app_client)

    filtros = [visiveis]
    if apenas_pendentes:
        # Pendente = direta não lida OU tarefa aberta.
        filtros.append(
            or_(
                and_(
                    Notificacao.escopo == NotifEscopo.DIRETA.value,
                    Notificacao.read_at.is_(None),
                ),
                and_(
                    Notificacao.escopo == NotifEscopo.TAREFA.value,
                    Notificacao.resolved_at.is_(None),
                ),
            )
        )

    total = (
        await session.scalar(
            select(func.count()).select_from(Notificacao).where(*filtros)
        )
    ) or 0

    result = await session.scalars(
        select(Notificacao)
        .where(*filtros)
        # `id` como último critério: created_at empata dentro do mesmo
        # lote e a paginação precisa ser determinística.
        .order_by(Notificacao.created_at.desc(), Notificacao.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    return paginated_response(
        items=[NotificacaoOut.model_validate(n) for n in result.all()],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get('/contador', response_model=ApiResponse[NotificacaoContador])
async def contador_notificacoes(
    session: Session,
    user: CurrentUser,
    active_org: ActiveOrgOptional,
    app_client: AppClient,
):
    """Contadores do sino — o MESMO predicado da lista, para nunca divergir."""
    visiveis = await condicoes_visiveis(session, user, active_org, app_client)

    nao_lidas = (
        await session.scalar(
            select(func.count())
            .select_from(Notificacao)
            .where(
                visiveis,
                Notificacao.escopo == NotifEscopo.DIRETA.value,
                Notificacao.read_at.is_(None),
            )
        )
    ) or 0
    tarefas = (
        await session.scalar(
            select(func.count())
            .select_from(Notificacao)
            .where(
                visiveis,
                Notificacao.escopo == NotifEscopo.TAREFA.value,
                Notificacao.resolved_at.is_(None),
            )
        )
    ) or 0

    return success_response(
        data=NotificacaoContador(
            nao_lidas=nao_lidas,
            tarefas=tarefas,
            total=nao_lidas + tarefas,
        )
    )


@router.patch(
    '/{notificacao_id}/lida', response_model=ApiResponse[NotificacaoOut]
)
async def marcar_lida(
    notificacao_id: int,
    session: Session,
    user: CurrentUser,
    app_client: AppClient,
):
    """Marca uma direta do próprio usuário como lida (idempotente).

    A query já amarra dono + audiência do app: notificação de terceiro ou
    do outro app responde 404 (não vaza nem a existência).
    """
    notif = await session.scalar(
        select(Notificacao).where(
            Notificacao.id == notificacao_id,
            Notificacao.escopo == NotifEscopo.DIRETA.value,
            Notificacao.user_id == user.id,
            Notificacao.audiencia == audiencia_do_app(app_client),
        )
    )
    if not notif:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Notificação não encontrada',
        )

    if notif.read_at is None:
        notif.read_at = datetime.now(timezone.utc)
        await session.commit()

    return success_response(data=NotificacaoOut.model_validate(notif))


@router.delete('/{notificacao_id}', response_model=ApiResponse[None])
async def apagar_notificacao(
    notificacao_id: int,
    session: Session,
    user: CurrentUser,
    app_client: AppClient,
):
    """Apaga uma direta do próprio usuário.

    Mesma amarra do `marcar_lida` (dono + audiência do app): notificação
    de terceiro, do outro app ou tarefa responde 404. Tarefa não se
    apaga — é compartilhada; o desfecho dela é o `/resolver`.
    """
    notif = await session.scalar(
        select(Notificacao).where(
            Notificacao.id == notificacao_id,
            Notificacao.escopo == NotifEscopo.DIRETA.value,
            Notificacao.user_id == user.id,
            Notificacao.audiencia == audiencia_do_app(app_client),
        )
    )
    if not notif:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Notificação não encontrada',
        )

    # Auditoria ANTES do delete: é a única operação irreversível da
    # feature, e o log é o que sobra como prova de que a pessoa foi
    # notificada. Lê os campos com a linha ainda em memória.
    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='notificacoes',
        resource_id=notif.id,
        before={
            'tipo': notif.tipo,
            'uae': notif.uae,
            'titulo': notif.titulo,
            'audiencia': notif.audiencia,
        },
    )

    await session.delete(notif)
    await session.commit()

    return success_response(message='Notificação apagada')


@router.post('/marcar-todas-lidas', response_model=ApiResponse[None])
async def marcar_todas_lidas(
    session: Session,
    user: CurrentUser,
    app_client: AppClient,
):
    """Marca em lote as diretas não lidas do usuário (no app do token)."""
    result = await session.execute(
        update(Notificacao)
        .where(
            Notificacao.escopo == NotifEscopo.DIRETA.value,
            Notificacao.user_id == user.id,
            Notificacao.audiencia == audiencia_do_app(app_client),
            Notificacao.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await session.commit()

    return success_response(
        message=f'{result.rowcount} notificação(ões) marcada(s) como lida(s)'
    )


@router.post(
    '/{notificacao_id}/resolver',
    response_model=ApiResponse[NotificacaoOut],
)
async def resolver_notificacao(
    notificacao_id: int,
    session: Session,
    user: CurrentUser,
    active_org: ActiveOrgOptional,
    app_client: AppClient,
):
    """Resolve uma tarefa da org ativa (idempotente).

    O guard é `has_org_permission` com argumentos DINÂMICOS (vêm da
    própria linha): a tarefa é endereçada por permissão, então só quem a
    possui — ou o admin da org, por bypass — pode dar o desfecho. Por ser
    dinâmico, não entra no catálogo `rbac-resources.json`.

    A query amarra escopo tarefa + audiência do app + `uae == active_org`:
    token do FatBird (audiência tripulante) e tarefa de outra org caem em
    404 antes de qualquer checagem de permissão.
    """
    notif = await session.scalar(
        select(Notificacao).where(
            Notificacao.id == notificacao_id,
            Notificacao.escopo == NotifEscopo.TAREFA.value,
            Notificacao.audiencia == audiencia_do_app(app_client),
            Notificacao.uae == active_org,
        )
    )
    if not notif:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Notificação não encontrada',
        )

    permitido = await has_org_permission(
        user, session, active_org, notif.req_resource, notif.req_action
    )
    if not permitido:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=(
                f'Permissão negada: {notif.req_resource}.{notif.req_action}'
            ),
        )

    if notif.resolved_at is None:
        notif.resolved_by = user.id
        notif.resolved_at = datetime.now(timezone.utc)
        # Auditoria no MESMO commit da resolução (contrato add-sem-commit
        # de `log_user_action`): rollback desfaz os dois juntos.
        await log_user_action(
            session=session,
            user_id=user.id,
            action='resolve',
            resource='notificacoes',
            resource_id=notif.id,
            after={
                'tipo': notif.tipo,
                'uae': notif.uae,
                'chave_dedupe': notif.chave_dedupe,
            },
        )
        await session.commit()

    return success_response(data=NotificacaoOut.model_validate(notif))
