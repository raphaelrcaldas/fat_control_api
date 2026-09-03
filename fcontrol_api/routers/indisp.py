from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.enums.notificacao import NotifAudiencia, NotifTipo
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import Etapa, OIEtapa, TripEtapa
from fcontrol_api.models.shared.indisp import Indisp
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.indisp import (
    BaseIndisp,
    IndispCrewEntry,
    IndispOut,
    IndispSchema,
    IndispTripInfo,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.security import (
    ActiveOrg,
    ensure_org_permission_or_owner,
    get_current_user,
    has_org_permission,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.services.notificacoes import notificar_usuarios
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix='/indisp', tags=['indisp'])

# Prazo mínimo que o próprio tripulante tem de respeitar para lançar,
# alterar ou remover a sua indisponibilidade: a escala já foi montada em
# cima dela. Quem tem a permissão 'ops.indisp' (escalante, pelo client)
# passa por cima — a trava é do token de tripulante.
PRAZO_MINIMO_DIAS = 2

# O fuso é explícito de propósito: o container roda em UTC, então
# `date.today()` viraria o dia seguinte às 21h de Brasília e endureceria a
# janela em um dia inteiro para quem lança à noite.
FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')


def data_minima_tripulante() -> date:
    """Primeira data que o tripulante ainda pode mexer por conta própria."""
    return datetime.now(FUSO_LOCAL).date() + timedelta(days=PRAZO_MINIMO_DIAS)


async def ensure_prazo_tripulante(
    user: User,
    session: AsyncSession,
    active_org: str | None,
    action: str,
    owner_id: int,
    datas: list[date],
) -> None:
    """Aplica o prazo mínimo a quem age como dono, sem gestão da escala.

    `datas` traz os inícios envolvidos na operação: o que está salvo (a
    indisponibilidade não pode estar dentro da janela) e o que se pretende
    gravar (não pode ser movida para dentro dela).
    """
    if user.id != owner_id:
        return

    if await has_org_permission(
        user, session, active_org, 'ops.indisp', action
    ):
        return

    minima = data_minima_tripulante()
    if all(d >= minima for d in datas):
        return

    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail=(
            f'Fora do prazo: você só altera indisponibilidades que comecem '
            f'a partir de {minima.strftime("%d/%m/%Y")}. '
            f'Para mudanças mais próximas, procure o escalante.'
        ),
    )


@router.get('/', response_model=ApiResponse[list[IndispCrewEntry]])
async def get_crew_indisp(
    session: Session,
    funcao: str,
    active_org: ActiveOrg,
    date_from: date | None = None,
    date_to: date | None = None,
):
    # Janela de dados. O client (Opção A) envia [date_from, date_to] e
    # navega apenas dentro dela. Sem date_from, preserva o comportamento
    # antigo (últimos 30 dias em diante).
    if date_from is None:
        date_from = date.today() - timedelta(days=30)

    # 1. Query principal para buscar os tripulantes e seus dados
    # relacionados (exceto indisps)
    trip_query = (
        select(Tripulante)
        .join(Tripulante.user)
        .join(User.posto)
        .options(
            selectinload(Tripulante.user).selectinload(User.posto),
        )
        .where(
            and_(
                (Tripulante.func == funcao),
                (Tripulante.uae == active_org),
                (Tripulante.active),
                (User.active),
            )
        )
        .order_by(
            PostoGrad.ant.asc(),
            User.ult_promo.asc(),
            User.ant_rel.asc(),
        )
    )

    result = await session.scalars(trip_query)
    tripulantes = result.unique().all()

    if not tripulantes:
        return success_response(data=[])

    # 2. Extrai os IDs dos usuários e tripulantes para as próximas queries.
    user_ids = [trip.user_id for trip in tripulantes]
    trip_ids = [trip.id for trip in tripulantes]

    # 3. Query batch para cemal + data_ult_voo (excluindo simuladores)
    sim_etapa_ids = (
        select(OIEtapa.etapa_id)
        .join(EsforcoAereo, EsforcoAereo.id == OIEtapa.esf_aer_id)
        .where(EsforcoAereo.descricao.contains('SML'))
        .scalar_subquery()
    )
    cemal_voo_query = (
        select(
            Tripulante.id.label('trip_id'),
            CartaoSaude.cemal,
            sql_func
            .max(Etapa.data)
            .filter(~Etapa.id.in_(sim_etapa_ids))
            .label('data_ult_voo'),
        )
        .select_from(Tripulante)
        .outerjoin(CartaoSaude, CartaoSaude.user_id == Tripulante.user_id)
        .outerjoin(TripEtapa, TripEtapa.trip_id == Tripulante.id)
        .outerjoin(Etapa, Etapa.id == TripEtapa.etapa_id)
        .where(Tripulante.id.in_(trip_ids))
        .group_by(Tripulante.id, CartaoSaude.cemal)
    )
    cemal_result = await session.execute(cemal_voo_query)
    cemal_by_trip = {
        row.trip_id: {
            'cemal': row.cemal,
            'data_ult_voo': row.data_ult_voo,
        }
        for row in cemal_result.all()
    }

    # 4. Uma única query para buscar todas as indisponibilidades relevantes,
    #    já carregando o usuário que a criou e o posto desse usuário.
    #    Traz tudo que sobrepõe a janela [date_from, date_to].
    indisp_filters = [
        Indisp.user_id.in_(user_ids),
        Indisp.date_end >= date_from,
    ]
    if date_to is not None:
        indisp_filters.append(Indisp.date_start <= date_to)

    indisp_query = (
        select(Indisp)
        .options(selectinload(Indisp.user_created).selectinload(User.posto))
        .where(*indisp_filters)
    )
    indisps_result = await session.scalars(indisp_query)

    # 5. Agrupa as indisponibilidades por user_id em um dicionário para
    # acesso rápido
    indisps_by_user = defaultdict(list)
    for indisp in indisps_result:
        indisps_by_user[indisp.user_id].append(
            IndispOut.model_validate(indisp)
        )

    # 6. Monta a resposta final
    response = []
    for trip in tripulantes:
        user_indisps = indisps_by_user.get(trip.user_id, [])
        user_indisps.sort(key=lambda i: i.date_end, reverse=True)

        trip_extra = cemal_by_trip.get(
            trip.id, {'cemal': None, 'data_ult_voo': None}
        )

        trip_info = IndispTripInfo(
            id=trip.id,
            trig=trip.trig,
            user=UserPublic.model_validate(trip.user),
            func=trip.func,
            oper=trip.oper,
            proj=trip.proj,
            data_op=trip.data_op,
            cemal=trip_extra.get('cemal'),
            data_ult_voo=trip_extra.get('data_ult_voo'),
        )

        response.append(IndispCrewEntry(trip=trip_info, indisps=user_indisps))

    return success_response(data=response)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[None],
)
async def create_indisp(
    indisp: IndispSchema,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
):
    # O tripulante lança a PRÓPRIA indisponibilidade pelo FatBird (sem
    # role); lançar para outro militar exige 'ops.indisp.create'.
    await ensure_org_permission_or_owner(
        user, session, active_org, 'ops.indisp', 'create', indisp.user_id
    )

    # O alvo tem de ser tripulante da org ativa — barra cross-org mesmo
    # para quem tem a permissão.
    alvo = await session.scalar(
        select(Tripulante).where(
            Tripulante.user_id == indisp.user_id,
            Tripulante.uae == active_org,
        )
    )
    if not alvo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante nao encontrado',
        )

    if indisp.date_end < indisp.date_start:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data Fim deve ser maior ou igual a data início',
        )

    await ensure_prazo_tripulante(
        user,
        session,
        active_org,
        'create',
        indisp.user_id,
        [indisp.date_start],
    )

    db_indisp = await session.scalar(
        select(Indisp).where(
            (Indisp.user_id == indisp.user_id),
            (Indisp.date_start == indisp.date_start),
            (Indisp.date_end == indisp.date_end),
            (Indisp.mtv == indisp.mtv),
            (Indisp.deleted_at.is_(None)),
        )
    )

    if db_indisp:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Indisponibilidade já registrada',
        )

    new_indisp = Indisp(
        user_id=indisp.user_id,
        date_start=indisp.date_start,
        date_end=indisp.date_end,
        mtv=indisp.mtv,
        obs=indisp.obs,
        created_by=user.id,
    )  # type: ignore

    session.add(new_indisp)

    # Flush (não commit) só para materializar o id: ele é o `recurso_id`
    # que leva o deep-link do sino à página da indisponibilidade.
    await session.flush()

    # Audiência 'tripulante': o sino só existe no FatBird — emitir para
    # gestor mandaria o aviso a um consumidor que não existe no client.
    await notificar_usuarios(
        session,
        user_ids=[new_indisp.user_id],
        uae=active_org,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        tipo=NotifTipo.INDISP_CRIADA.value,
        titulo='Nova indisponibilidade lançada para você',
        descricao=(
            f'Período de {indisp.date_start.strftime("%d/%m/%Y")} a '
            f'{indisp.date_end.strftime("%d/%m/%Y")}.'
        ),
        recurso='ops.indisp',
        recurso_id=new_indisp.id,
        # Dado CRU: o motivo vai como código ('sde', 'fer'…) porque o mapa
        # de rótulos e a rota são decisão do front. Datas em ISO: o payload
        # é JSONB e `date` não serializa sozinho.
        payload={
            'mtv': indisp.mtv.value,
            'date_start': indisp.date_start.isoformat(),
            'date_end': indisp.date_end.isoformat(),
        },
        # O serviço já pula alvo == created_by: quem lança a própria
        # indisponibilidade pelo FatBird não se autonotifica.
        created_by=user.id,
    )

    # Commit ÚNICO para a indisponibilidade + a notificação: rollback leva
    # as duas juntas (contrato de `services/notificacoes.py`).
    await session.commit()

    return success_response(
        message='Indisponibilidade adicionada com sucesso',
    )


@router.get('/user/{id}', response_model=ApiResponse[list[IndispOut]])
async def get_indisp_user(
    id: int,
    session: Session,
    active_org: ActiveOrg,
    date_from: date | None = None,
    date_to: date | None = None,
    mtv: str | None = None,
):
    # Leitura fica aberta dentro da org (a lista de tripulação já expõe as
    # indisponibilidades de todos, e o tripulante não tem role) — mas o
    # alvo precisa ser da org ativa, senão vaza cross-org. Fora do escopo
    # devolve lista vazia (é rota de lista): não vaza a existência do
    # militar nem quebra quem consulta um não-tripulante.
    alvo = await session.scalar(
        select(Tripulante).where(
            Tripulante.user_id == id,
            Tripulante.uae == active_org,
        )
    )
    if not alvo:
        return success_response(data=[])

    # Construção dinâmica dos filtros
    filters = [Indisp.user_id == id]

    if date_from:
        filters.append(Indisp.date_end >= date_from)

    if date_to:
        filters.append(Indisp.date_start <= date_to)

    if mtv:
        filters.append(Indisp.mtv == mtv)

    db_indisps = await session.scalars(
        select(Indisp).where(and_(*filters)).order_by(Indisp.date_end.desc())
    )

    indisps = db_indisps.all()

    return success_response(data=list(indisps))


@router.get('/{id}', response_model=ApiResponse[IndispOut])
async def get_indisp(
    id: int,
    session: Session,
    active_org: ActiveOrg,
):
    # Sem gate de permissão, mesmo racional do `/user/{id}` acima: a lista
    # de tripulação já expõe a indisponibilidade de todos e o tripulante do
    # FatBird não tem role — gatear trancaria o portal.
    #
    # O escopo, então, tem de vir da QUERY (mesmo join do PUT/DELETE): o id
    # é sequencial e sem o `Tripulante.uae == active_org` qualquer token
    # válido leria a indisponibilidade de qualquer militar do sistema.
    indisp = await session.scalar(
        select(Indisp)
        .join(Tripulante, Tripulante.user_id == Indisp.user_id)
        .where(Indisp.id == id, Tripulante.uae == active_org)
    )

    # `deleted_at` NÃO entra no filtro de propósito: o deep-link do sino
    # sobrevive à remoção, e a página precisa da linha excluída para dizer
    # que a indisponibilidade foi removida (`IndispOut` expõe o campo).
    if not indisp:
        # Rota de ITEM: fora do escopo é 404, não lista vazia.
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Indisponibilidade não encontrada',
        )

    return success_response(data=indisp)


@router.delete('/{id}', response_model=ApiResponse[None])
async def delete_indisp(
    id: int,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
):
    indisp = await session.scalar(
        select(Indisp)
        .join(Tripulante, Tripulante.user_id == Indisp.user_id)
        .where(Indisp.id == id, Tripulante.uae == active_org)
    )

    if not indisp:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Indisponibilidade não encontrada',
        )

    # O dono remove a própria (FatBird); remover a de outro exige
    # 'ops.indisp.delete' na org ativa.
    await ensure_org_permission_or_owner(
        user, session, active_org, 'ops.indisp', 'delete', indisp.user_id
    )

    await ensure_prazo_tripulante(
        user,
        session,
        active_org,
        'delete',
        indisp.user_id,
        [indisp.date_start],
    )

    # Soft delete - setar deleted_at
    indisp.deleted_at = datetime.now(timezone.utc)

    # Log de deleção COM o estado apagado em `before`: o soft delete tira a
    # linha da tela, e sem isto o histórico registrava só "fulano removeu
    # em tal hora", sem dizer o quê. `after` fica vazio de propósito — é o
    # que distingue uma remoção de uma alteração para quem lê o log.
    # Datas viram string para serializar em JSONB, igual ao `patch` acima.
    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='ops.indisp',
        resource_id=indisp.id,
        before={
            'date_start': str(indisp.date_start),
            'date_end': str(indisp.date_end),
            'mtv': indisp.mtv,
            'obs': indisp.obs,
        },
    )

    # Valores ainda em memória: o soft delete não apaga a linha, então o
    # payload leva o período que deixou de valer.
    await notificar_usuarios(
        session,
        user_ids=[indisp.user_id],
        uae=active_org,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        tipo=NotifTipo.INDISP_REMOVIDA.value,
        titulo='Sua indisponibilidade foi removida',
        descricao=(
            f'Período de {indisp.date_start.strftime("%d/%m/%Y")} a '
            f'{indisp.date_end.strftime("%d/%m/%Y")}.'
        ),
        recurso='ops.indisp',
        recurso_id=indisp.id,
        payload={
            'mtv': indisp.mtv,
            'date_start': indisp.date_start.isoformat(),
            'date_end': indisp.date_end.isoformat(),
        },
        created_by=user.id,
    )

    # Commit ÚNICO: se a remoção falhar, o aviso não sobrevive sozinho.
    await session.commit()

    return success_response(message='Indisponibilidade deletada')


@router.put('/{id}', response_model=ApiResponse[None])
async def update_indisp(
    id: int,
    indisp: BaseIndisp,
    session: Session,
    active_org: ActiveOrg,
    user: CurrentUser,
):
    db_indisp = await session.scalar(
        select(Indisp)
        .join(Tripulante, Tripulante.user_id == Indisp.user_id)
        .where(Indisp.id == id, Tripulante.uae == active_org)
    )

    if not db_indisp:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Indisponibilidade não encontrada',
        )

    # O dono edita a própria (FatBird); editar a de outro exige
    # 'ops.indisp.update' na org ativa.
    await ensure_org_permission_or_owner(
        user, session, active_org, 'ops.indisp', 'update', db_indisp.user_id
    )

    if db_indisp.deleted_at is not None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Impossível atualizar, indisponibilidade excluída',
        )

    # Só as chaves realmente enviadas entram na atualização. `obs` é a
    # única coluna anulável: nela um None explícito significa "limpar" e
    # precisa ser aplicado. Nas demais, None é campo ausente do formulário.
    campos = indisp.model_dump(exclude_unset=True)
    for key in ('date_start', 'date_end', 'mtv'):
        if campos.get(key) is None:
            campos.pop(key, None)

    # Valores resultantes da alteração — base da validação e da checagem de
    # duplicata.
    check_date_start = campos.get('date_start', db_indisp.date_start)
    check_date_end = campos.get('date_end', db_indisp.date_end)
    check_mtv = campos.get('mtv', db_indisp.mtv)
    check_obs = campos.get('obs', db_indisp.obs)

    # Mesma regra do POST: sem ela dava para inverter o período por PUT
    # (payload parcial com só uma das pontas) e gravar fim antes do início.
    if check_date_end < check_date_start:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data Fim deve ser maior ou igual a data início',
        )

    # O prazo vale para o período salvo E para o pretendido: nem mexer no
    # que já está dentro da janela, nem puxar a indisponibilidade para
    # dentro dela.
    await ensure_prazo_tripulante(
        user,
        session,
        active_org,
        'update',
        db_indisp.user_id,
        [db_indisp.date_start, check_date_start],
    )

    ss_indisp = await session.scalar(
        select(Indisp).where(
            (Indisp.user_id == db_indisp.user_id)
            & (Indisp.date_start == check_date_start)
            & (Indisp.date_end == check_date_end)
            & (Indisp.mtv == check_mtv)
            & (Indisp.obs == check_obs)
            & (Indisp.deleted_at.is_(None))  # excluída não é duplicata
            & (Indisp.id != id)  # Exclui o próprio registro da verificação
        )
    )

    if ss_indisp:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Indisponibilidade já registrada',
        )

    # Captura os valores antes e depois da alteração
    before = {}
    after = {}
    for key, value in campos.items():
        old_value = getattr(db_indisp, key)
        if old_value != value:
            # Converte date para string para serialização JSON
            before[key] = (
                str(old_value)
                if hasattr(old_value, 'isoformat')
                else old_value
            )
            after[key] = str(value) if hasattr(value, 'isoformat') else value
            setattr(db_indisp, key, value)

    await log_user_action(
        session=session,
        user_id=user.id,
        action='patch',
        resource='ops.indisp',
        resource_id=db_indisp.id,
        before=before,
        after=after,
    )

    # Só notifica se houve diff real: PUT idempotente (payload igual ao que
    # já estava salvo) não é evento — avisar aí seria ruído no sino.
    if after:
        await notificar_usuarios(
            session,
            user_ids=[db_indisp.user_id],
            uae=active_org,
            audiencia=NotifAudiencia.TRIPULANTE.value,
            tipo=NotifTipo.INDISP_ALTERADA.value,
            titulo='Sua indisponibilidade foi alterada',
            # Valores JÁ atualizados (o `setattr` roda no laço do diff): o
            # aviso descreve como a indisponibilidade ficou.
            descricao=(
                f'Novo período: {db_indisp.date_start.strftime("%d/%m/%Y")}'
                f' a {db_indisp.date_end.strftime("%d/%m/%Y")}.'
            ),
            recurso='ops.indisp',
            recurso_id=db_indisp.id,
            payload={
                # `mtv` pode chegar aqui como membro do Enum (veio do dump
                # do schema) ou como str (não foi tocado). `str()` num
                # `str, Enum` devolveria 'IndispEnum.saude', não 'sde'.
                'mtv': getattr(db_indisp.mtv, 'value', db_indisp.mtv),
                'date_start': db_indisp.date_start.isoformat(),
                'date_end': db_indisp.date_end.isoformat(),
            },
            created_by=user.id,
        )

    # Commit ÚNICO: a notificação entra na mesma transação da alteração.
    await session.commit()

    return success_response(
        message='Indisponibilidade atualizada',
    )
