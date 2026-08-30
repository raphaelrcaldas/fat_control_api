from collections import defaultdict
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.enums.notificacao import NotifAudiencia, NotifTipo
from fcontrol_api.models.shared.funcoes import FuncaoUae
from fcontrol_api.models.shared.quads import (
    Quad,
    QuadsFunc,
    QuadsGroup,
    QuadsType,
)
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.ops.quads import (
    QuadBatchDelete,
    QuadOrfaoTripInfo,
    QuadPublic,
    QuadSchema,
    QuadsFuncsSet,
    QuadsGroupCreate,
    QuadsGroupOut,
    QuadsGroupSchema,
    QuadsGroupUpdate,
    QuadsOrfaoEntry,
    QuadsOrfaosDelete,
    QuadsOrfaosDeleteResponse,
    QuadsTypeCreate,
    QuadsTypeOut,
    QuadsTypeUpdate,
    QuadUpdate,
    TripQuadEntry,
    TripQuadInfo,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.services.notificacoes import notificar_usuarios
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])

ManageQuads = Depends(permission_checker('ops.quadrinhos', 'create'))
UpdateQuads = Depends(permission_checker('ops.quadrinhos', 'update'))
DeleteQuads = Depends(permission_checker('ops.quadrinhos', 'delete'))


@router.post(
    '/', status_code=HTTPStatus.CREATED, response_model=ApiResponse[None]
)
async def create_quad(
    quads: list[QuadSchema],
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, ManageQuads],
):
    # Escopo multi-tenant: todo trip_id do lote deve ser de tripulante da
    # org ativa — bloqueia gravar quadrinho em tripulante de outra unidade.
    # A MESMA query já traz `user_id` e `func` de cada tripulante para a
    # emissão da notificação adiante (evita select extra e, principalmente,
    # evita ler atributo lazy de ORM fora do greenlet).
    trip_ids = {quad.trip_id for quad in quads}
    rows = (
        await session.execute(
            select(Tripulante.id, Tripulante.user_id, Tripulante.func).where(
                Tripulante.id.in_(trip_ids),
                Tripulante.uae == active_org,
            )
        )
    ).all()
    trip_info = {tid: (uid, tfunc) for tid, uid, tfunc in rows}
    validos = set(trip_info)
    if trip_ids - validos:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado',
        )

    # Mesmo escopo para o TIPO: `quads_type` pende de um `quads_group`, que
    # é da org — sem esta amarra um gestor gravaria quadrinho de tipo de
    # outra unidade e o rótulo dela viajaria dentro do payload da
    # notificação entregue ao tripulante. A MESMA query devolve o `long`
    # usado no payload adiante: uma consulta só para o lote inteiro.
    type_ids = {quad.type_id for quad in quads}
    tipos_rotulo = {
        tid: (nome, grupo)
        for tid, nome, grupo in (
            await session.execute(
                select(QuadsType.id, QuadsType.long, QuadsGroup.long)
                .join(QuadsGroup, QuadsType.group_id == QuadsGroup.id)
                .where(
                    QuadsType.id.in_(type_ids),
                    QuadsGroup.uae == active_org,
                )
            )
        ).all()
    }
    if type_ids - set(tipos_rotulo):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tipo de quadrinho não encontrado',
        )

    insert_quads = []
    for quad in quads:
        if quad.value is not None:
            db_quad = await session.scalar(
                select(Quad).where(
                    (Quad.value == quad.value)
                    & (Quad.type_id == quad.type_id)
                    & (Quad.trip_id == quad.trip_id)
                )
            )

            if db_quad:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail='Quadrinho já registrado',
                )

        quad_db = Quad(
            value=quad.value,
            description=quad.description,
            type_id=quad.type_id,
            trip_id=quad.trip_id,
        )

        insert_quads.append(quad_db)

    session.add_all(insert_quads)

    # Notifica o tripulante no PORTAL (audiencia 'tripulante': quadrinho é
    # dado do FatBird, invisível no sino do client).
    #
    # Agrupado por (tripulante, TIPO), não só por tripulante: a tela lança
    # um tipo por vez para um tripulante — variando só a quantidade
    # (lastros ou intervalo de datas) —, mas o endpoint aceita lote
    # arbitrário. Agrupar pelo par mantém "uma notificação = um tipo"
    # verdadeiro por construção; sem isso um lote misto viraria um item só
    # com o deep-link apontando para um dos tipos, escolhido por acaso.
    quads_por_alvo: dict[tuple[int, int], list[QuadSchema]] = defaultdict(list)
    for quad in quads:
        quads_por_alvo[(quad.trip_id, quad.type_id)].append(quad)

    for (trip_id, type_id), itens in quads_por_alvo.items():
        # Só dados já em memória (payload validado + rows das queries de
        # validação) — nenhum atributo lazy de ORM, para não disparar
        # select assíncrono fora do greenlet.
        alvo_user_id, alvo_func = trip_info[trip_id]
        nome_tipo, nome_grupo = tipos_rotulo[type_id]
        qtd = len(itens)
        await notificar_usuarios(
            session,
            user_ids=[alvo_user_id],
            uae=active_org,
            audiencia=NotifAudiencia.TRIPULANTE.value,
            tipo=NotifTipo.QUADRO_RECEBIDO.value,
            titulo=f'Você recebeu {qtd} quadrinho(s)',
            recurso='ops.quadro',
            # `tipo` (id + nome + grupo) e `func` alimentam o deep-link do
            # FatBird (/ops/quads?tipo=&func=) e o rótulo do item no sino.
            # A ROTA e o TEXTO são montados pelo front: aqui vai o dado
            # CRU (nome como está no catálogo, minúsculo), porque caixa
            # alta é decisão de exibição — a tela de quadrinhos exibe o
            # mesmo rótulo em maiúsculas por classe CSS, não por dado.
            payload={
                'quantidade': qtd,
                'tipo': {
                    'id': type_id,
                    'nome': nome_tipo,
                    'grupo': nome_grupo,
                },
                'func': alvo_func,
            },
            # `notificar_usuarios` pula o alvo == created_by: quem lançou o
            # próprio quadrinho não recebe "você recebeu".
            created_by=user.id,
        )

    # Commit ÚNICO para quadrinhos + notificações: rollback da mutação
    # leva a notificação junto (contrato de `services/notificacoes.py`).
    await session.commit()

    return success_response(message='Quadrinho inserido com sucesso')


@router.get(
    '/trip/{trip_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[QuadPublic]],
)
async def quads_by_trip(
    trip_id: int,
    type_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    # Escopo por org: sem o join em Tripulante, qualquer autenticado lia o
    # quadrinho de tripulante de outra unidade só chutando o trip_id.
    query = (
        select(Quad)
        .join(Tripulante, Tripulante.id == Quad.trip_id)
        .where(
            (Quad.trip_id == trip_id)
            & (Quad.type_id == type_id)
            & (Tripulante.uae == active_org)
        )
        .order_by(
            Quad.value.desc().nulls_last()
        )  # valores em DESC, NULLs por último
    )

    result = await session.scalars(query)
    quads = result.all()

    return success_response(data=[QuadPublic.model_validate(q) for q in quads])


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[TripQuadEntry]],
)
async def list_quads(
    session: Session,
    active_org: ActiveOrg,
    tipo_quad: int = 1,  # sobr preto
    funcao: str = 'mc',
    proj: str | None = None,
):
    # 1. CTE para obter os IDs dos tripulantes que correspondem aos filtros
    trip_filters = [
        Tripulante.uae == active_org,
        Tripulante.active,
        Tripulante.func == funcao,
        Tripulante.oper != 'al',
        Tripulante.data_op.is_not(None),
    ]

    # Sem `proj`, o quadro considera todos os projetos operados pela org.
    if proj:
        trip_filters.append(Tripulante.proj == proj)

    trip_ids_cte = (
        select(Tripulante.id).where(*trip_filters).cte('trip_ids_cte')
    )

    # 2. CTE para contar o total de quadrinhos de cada tripulante
    quad_counts_cte = (
        select(Quad.trip_id, func.count(Quad.id).label('total_quads'))
        .where(
            Quad.trip_id.in_(select(trip_ids_cte.c.id)),
            Quad.type_id == tipo_quad,
        )
        .group_by(Quad.trip_id)
        .cte('quad_counts_cte')
    )

    # 3. Query principal para buscar os tripulantes e a contagem total
    # Faz um LEFT JOIN com a contagem, para incluir tripulantes sem quadrinhos
    trip_query = (
        select(Tripulante, quad_counts_cte.c.total_quads)
        .outerjoin(quad_counts_cte, Tripulante.id == quad_counts_cte.c.trip_id)
        .options(
            selectinload(Tripulante.user).selectinload(User.posto),
        )
        .where(Tripulante.id.in_(select(trip_ids_cte.c.id)))
        .order_by(Tripulante.data_op, Tripulante.id)
    )

    trips_result = await session.execute(trip_query)
    trip_data = (
        trips_result.unique().all()
    )  # Retorna tuplas (Tripulante, total_quads)

    if not trip_data:
        return success_response(data=[])

    # Extrai os IDs e o min_length dos resultados
    trip_ids = [trip.id for trip, _ in trip_data]
    min_length = min(
        (total_quads if total_quads is not None else 0)
        for _, total_quads in trip_data
    )

    # 4. Query avançada para buscar APENAS os quadrinhos já fatiados
    n_slice = 0 if min_length == 0 else min_length - 1

    # CTE para rankear os quadrinhos
    ranked_quads_cte = (
        select(
            Quad,
            func
            .row_number()
            .over(
                partition_by=Quad.trip_id,
                order_by=Quad.value.asc().nullsfirst(),
            )
            .label('rn'),
        )
        .where(Quad.trip_id.in_(trip_ids), Quad.type_id == tipo_quad)
        .cte('ranked_quads')
    )

    # Query final para buscar os quadrinhos já fatiados
    final_quads_query = select(ranked_quads_cte).where(
        ranked_quads_cte.c.rn > n_slice
    )

    quads_result = await session.execute(final_quads_query)
    all_quads_data = quads_result.mappings()

    # 5. Agrupa os dicionários de dados por trip_id
    quads_by_trip_id = defaultdict(list)
    for q_data in all_quads_data:
        quads_by_trip_id[q_data['trip_id']].append(q_data)

    # 6. Monta a resposta final
    response = []
    for trip, total_quads in trip_data:
        trip_info = TripQuadInfo.model_validate(trip)

        response.append(
            TripQuadEntry(
                trip=trip_info,
                quads=[
                    QuadPublic.model_validate(q)
                    for q in quads_by_trip_id[trip.id]
                ],
                quads_len=total_quads if total_quads is not None else 0,
            )
        )

    return success_response(data=response)


@router.get(
    '/orfaos',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[QuadsOrfaoEntry]],
    dependencies=[ManageQuads],
)
async def list_orphan_quads(session: Session, active_org: ActiveOrg):
    query = (
        select(Tripulante, func.count(Quad.id).label('quads_count'))
        .join(Quad, Quad.trip_id == Tripulante.id)
        .where(
            Tripulante.uae == active_org,
            Tripulante.active.is_(False),
        )
        .group_by(Tripulante.id)
        .options(selectinload(Tripulante.user).selectinload(User.posto))
        .order_by(Tripulante.id)
    )

    result = await session.execute(query)
    rows = result.all()

    # A função é omitida: tripulante desativado não tem função operacional
    # relevante no contexto de limpeza de órfãos.
    response = [
        QuadsOrfaoEntry(
            trip=QuadOrfaoTripInfo.model_validate(trip),
            quads_count=quads_count,
        )
        for trip, quads_count in rows
    ]

    return success_response(data=response)


@router.delete(
    '/orfaos',
    response_model=ApiResponse[QuadsOrfaosDeleteResponse],
    dependencies=[ManageQuads],
)
async def delete_orphan_quads(
    payload: QuadsOrfaosDelete, session: Session, active_org: ActiveOrg
):
    valid_ids_q = select(Tripulante.id).where(
        Tripulante.id.in_(payload.trip_ids),
        Tripulante.uae == active_org,
        Tripulante.active.is_(False),
    )
    valid_ids = (await session.execute(valid_ids_q)).scalars().all()

    deleted = 0
    if valid_ids:
        result = await session.execute(
            delete(Quad).where(Quad.trip_id.in_(valid_ids))
        )
        await session.commit()
        deleted = result.rowcount

    return success_response(
        data=QuadsOrfaosDeleteResponse(deleted=deleted, trips=len(valid_ids)),
        message=(
            f'{deleted} quadrinho(s) de {len(valid_ids)} '
            f'tripulante(s) removido(s)'
        ),
    )


@router.delete('/', response_model=ApiResponse[None])
async def delete_quads(
    body: QuadBatchDelete,
    session: Session,
    active_org: ActiveOrg,
    user: Annotated[User, DeleteQuads],
):
    # Lê ANTES de apagar: é a única janela para saber a quem a remoção
    # interessa (o quad guarda `trip_id`, mas a notificação vai para o
    # `user_id`) e qual tipo saiu. O escopo de org é o mesmo de antes —
    # id de outra unidade não entra na lista e, portanto, não é apagado.
    alvos = (
        await session.execute(
            select(
                Quad.id,
                Quad.type_id,
                Quad.trip_id,
                Tripulante.user_id,
                Tripulante.func,
            )
            .join(Tripulante, Tripulante.id == Quad.trip_id)
            .where(Quad.id.in_(body.ids), Tripulante.uae == active_org)
        )
    ).all()

    if not alvos:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Nenhum quadrinho encontrado',
        )

    await session.execute(
        delete(Quad).where(Quad.id.in_([row.id for row in alvos]))
    )

    # Rótulo dos tipos removidos, numa consulta só. O join em
    # `quads_group` mantém o mesmo escopo de org do lançamento.
    tipos_rotulo = {
        tid: (nome, grupo)
        for tid, nome, grupo in (
            await session.execute(
                select(QuadsType.id, QuadsType.long, QuadsGroup.long)
                .join(QuadsGroup, QuadsType.group_id == QuadsGroup.id)
                .where(
                    QuadsType.id.in_({row.type_id for row in alvos}),
                    QuadsGroup.uae == active_org,
                )
            )
        ).all()
    }

    # Mesmo agrupamento do lançamento — (tripulante, tipo) —, para o item
    # do sino dizer QUAL quadrinho saiu e levar ao lugar certo.
    removidos: dict[tuple[int, int], int] = defaultdict(int)
    info_alvo: dict[int, tuple[int, str]] = {}
    for row in alvos:
        removidos[(row.trip_id, row.type_id)] += 1
        info_alvo[row.trip_id] = (row.user_id, row.func)

    for (trip_id, type_id), qtd in removidos.items():
        nome_tipo, nome_grupo = tipos_rotulo[type_id]
        alvo_user_id, alvo_func = info_alvo[trip_id]
        await notificar_usuarios(
            session,
            user_ids=[alvo_user_id],
            uae=active_org,
            audiencia=NotifAudiencia.TRIPULANTE.value,
            tipo=NotifTipo.QUADRO_REMOVIDO.value,
            titulo=f'Foram removidos {qtd} quadrinho(s)',
            recurso='ops.quadro',
            payload={
                'quantidade': qtd,
                'tipo': {
                    'id': type_id,
                    'nome': nome_tipo,
                    'grupo': nome_grupo,
                },
                'func': alvo_func,
            },
            created_by=user.id,
        )

    # Commit ÚNICO: se a remoção falhar, o aviso não sobrevive sozinho.
    await session.commit()

    return success_response(message=f'{len(alvos)} quadrinho(s) deletado(s)')


@router.put('/{id}', response_model=ApiResponse[None])
async def update_quad(
    id: int,
    quad: QuadUpdate,
    session: Session,
    active_org: ActiveOrg,
    _: Annotated[User, UpdateQuads],
):
    # Escopo: o quadrinho deve pertencer a tripulante da org ativa.
    db_quad = await session.scalar(
        select(Quad)
        .join(Tripulante, Tripulante.id == Quad.trip_id)
        .where(Quad.id == id, Tripulante.uae == active_org)
    )

    if not db_quad:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Quadrinho não encontrado',
        )

    # Remanejar para outro tripulante só dentro da própria org.
    trip_ok = await session.scalar(
        select(Tripulante.id).where(
            Tripulante.id == quad.trip_id,
            Tripulante.uae == active_org,
        )
    )
    if not trip_ok:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tripulante não encontrado',
        )

    ss_quad = await session.scalar(
        select(Quad).where(
            (Quad.value == quad.value)
            & (Quad.type_id == db_quad.type_id)
            & (Quad.trip_id == quad.trip_id)
            & (Quad.id != id)
        )
    )

    if ss_quad:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Quadrinho já registrado',
        )

    for key, value in quad.model_dump(exclude_unset=True).items():
        if getattr(db_quad, key) != value:
            setattr(db_quad, key, value)

    await session.commit()

    return success_response(message='Quadrinho atualizado')


@router.get('/types', response_model=ApiResponse[list[QuadsGroupSchema]])
async def get_quads_type(session: Session, active_org: ActiveOrg):
    result = await session.scalars(
        select(QuadsGroup)
        .where(QuadsGroup.uae == active_org)
        .options(selectinload(QuadsGroup.types).selectinload(QuadsType.funcs))
    )
    groups = result.all()

    for group in groups:
        group.types = sorted(group.types, key=lambda x: x.id)

        for type_quad in group.types:
            # Dedup defensivo: dados legados podem ter linhas duplicadas em
            # quads_func (mesmo type_id + func). dict.fromkeys preserva ordem.
            funcs = list(dict.fromkeys(e.func for e in type_quad.funcs))
            setattr(type_quad, 'funcs_list', funcs)

    return success_response(data=list(groups))


# ===========================================================================
# Gerenciamento da estrutura de quadrinhos (Group -> Type -> Func)
#
# Escopo: usuário com permissão `ops.quadrinhos.create`, restrito à organização
# ativa (QuadsGroup.uae). Deleções bloqueiam quando há dependências (409),
# sem cascade. A associação de funções é declarativa (substitui o conjunto).
# ===========================================================================


async def _get_group_scoped(
    group_id: int, session: AsyncSession, active_org: str
) -> QuadsGroup:
    group = await session.get(QuadsGroup, group_id)
    if not group or group.uae != active_org:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Grupo de quadrinhos não encontrado',
        )
    return group


async def _get_type_scoped(
    type_id: int, session: AsyncSession, active_org: str
) -> QuadsType:
    type_db = await session.scalar(
        select(QuadsType)
        .join(QuadsGroup, QuadsType.group_id == QuadsGroup.id)
        .where(QuadsType.id == type_id, QuadsGroup.uae == active_org)
    )
    if not type_db:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tipo de quadrinho não encontrado',
        )
    return type_db


async def _type_funcs(type_id: int, session: AsyncSession) -> list[str]:
    rows = await session.scalars(
        select(QuadsFunc.func).where(QuadsFunc.type_id == type_id)
    )
    return list(rows)


def _type_out(type_db: QuadsType, funcs_list: list[str]) -> QuadsTypeOut:
    # funcs_list não é atributo do model (QuadsType expõe a relationship
    # `funcs`), por isso o Out é montado explicitamente.
    return QuadsTypeOut(
        id=type_db.id,
        group_id=type_db.group_id,
        short=type_db.short,
        long=type_db.long,
        funcs_list=funcs_list,
    )


@router.post(
    '/groups',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[QuadsGroupOut],
    dependencies=[ManageQuads],
)
async def create_quads_group(
    body: QuadsGroupCreate, session: Session, active_org: ActiveOrg
):
    group = QuadsGroup(short=body.short, long=body.long, uae=active_org)
    session.add(group)
    await session.commit()
    await session.refresh(group)

    return success_response(
        data=QuadsGroupOut.model_validate(group),
        message='Grupo de quadrinhos criado',
    )


@router.put(
    '/groups/{group_id}',
    response_model=ApiResponse[QuadsGroupOut],
    dependencies=[ManageQuads],
)
async def update_quads_group(
    group_id: int,
    body: QuadsGroupUpdate,
    session: Session,
    active_org: ActiveOrg,
):
    group = await _get_group_scoped(group_id, session, active_org)

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(group, key, value)

    await session.commit()
    await session.refresh(group)

    return success_response(
        data=QuadsGroupOut.model_validate(group),
        message='Grupo de quadrinhos atualizado',
    )


@router.delete(
    '/groups/{group_id}',
    response_model=ApiResponse[None],
    dependencies=[ManageQuads],
)
async def delete_quads_group(
    group_id: int, session: Session, active_org: ActiveOrg
):
    group = await _get_group_scoped(group_id, session, active_org)

    has_type = await session.scalar(
        select(QuadsType.id).where(QuadsType.group_id == group_id).limit(1)
    )
    if has_type:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Grupo possui tipos de quadrinho. Remova os tipos antes '
                'de excluir o grupo.'
            ),
        )

    await session.delete(group)
    await session.commit()

    return success_response(message='Grupo de quadrinhos removido')


@router.post(
    '/groups/{group_id}/types',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[QuadsTypeOut],
    dependencies=[ManageQuads],
)
async def create_quads_type(
    group_id: int,
    body: QuadsTypeCreate,
    session: Session,
    active_org: ActiveOrg,
):
    await _get_group_scoped(group_id, session, active_org)

    type_db = QuadsType(group_id=group_id, short=body.short, long=body.long)
    session.add(type_db)
    await session.commit()
    await session.refresh(type_db)

    return success_response(
        data=_type_out(type_db, []),
        message='Tipo de quadrinho criado',
    )


@router.put(
    '/types/{type_id}',
    response_model=ApiResponse[QuadsTypeOut],
    dependencies=[ManageQuads],
)
async def update_quads_type(
    type_id: int,
    body: QuadsTypeUpdate,
    session: Session,
    active_org: ActiveOrg,
):
    type_db = await _get_type_scoped(type_id, session, active_org)

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(type_db, key, value)

    await session.commit()
    await session.refresh(type_db)
    funcs_list = await _type_funcs(type_id, session)

    return success_response(
        data=_type_out(type_db, funcs_list),
        message='Tipo de quadrinho atualizado',
    )


@router.delete(
    '/types/{type_id}',
    response_model=ApiResponse[None],
    dependencies=[ManageQuads],
)
async def delete_quads_type(
    type_id: int, session: Session, active_org: ActiveOrg
):
    type_db = await _get_type_scoped(type_id, session, active_org)

    has_quad = await session.scalar(
        select(Quad.id).where(Quad.type_id == type_id).limit(1)
    )
    if has_quad:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Tipo possui quadrinhos registrados de tripulantes. '
                'Remova-os antes de excluir o tipo.'
            ),
        )

    await session.execute(
        delete(QuadsFunc).where(QuadsFunc.type_id == type_id)
    )
    await session.delete(type_db)
    await session.commit()

    return success_response(message='Tipo de quadrinho removido')


@router.put(
    '/types/{type_id}/funcs',
    response_model=ApiResponse[QuadsTypeOut],
    dependencies=[ManageQuads],
)
async def set_quads_type_funcs(
    type_id: int,
    body: QuadsFuncsSet,
    session: Session,
    active_org: ActiveOrg,
):
    type_db = await _get_type_scoped(type_id, session, active_org)

    # Dedup preservando a ordem informada.
    novas_funcs = list(dict.fromkeys(f.lower() for f in body.funcs))

    # Só concorre ao quadrinho função que a unidade opera (funcoes_uae).
    if novas_funcs:
        operadas = set(
            await session.scalars(
                select(FuncaoUae.func_cod).where(
                    FuncaoUae.uae == active_org,
                    FuncaoUae.func_cod.in_(novas_funcs),
                    FuncaoUae.active.is_(True),
                )
            )
        )
        invalidas = [f for f in novas_funcs if f not in operadas]
        if invalidas:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'Função não operada pela organização: '
                    f'{", ".join(invalidas)}'
                ),
            )

    await session.execute(
        delete(QuadsFunc).where(QuadsFunc.type_id == type_id)
    )
    session.add_all([QuadsFunc(type_id=type_id, func=f) for f in novas_funcs])
    await session.commit()

    return success_response(
        data=_type_out(type_db, novas_funcs),
        message='Funções do quadrinho atualizadas',
    )
