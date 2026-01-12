from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.funcoes import BaseFunc
from fcontrol_api.schemas.indisp import BaseIndisp, IndispOut, IndispSchema
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.security import get_current_user
from fcontrol_api.services.logs import log_user_action

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/indisp', tags=['indisp'])


@router.get('/')
async def get_crew_indisp(session: Session, funcao: str, uae: str):
    date_ini = date.today() - timedelta(days=30)

    # 1. Query principal para buscar os tripulantes e seus dados
    # relacionados (exceto indisps)
    trip_query = (
        select(Tripulante)
        .join(Tripulante.funcs)
        .join(Tripulante.user)
        .join(User.posto)
        .options(
            selectinload(Tripulante.user).selectinload(User.posto),
            selectinload(Tripulante.funcs),
        )
        .where(
            and_(
                (Funcao.func == funcao),
                (Tripulante.uae == uae),
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
        return []

    # 2. Extrai os IDs dos usuários para a próxima query.
    user_ids = [trip.user_id for trip in tripulantes]

    # 3. Uma única query para buscar todas as indisponibilidades relevantes,
    #    já carregando o usuário que a criou e o posto desse usuário.
    indisp_query = (
        select(Indisp)
        .options(selectinload(Indisp.user_created).selectinload(User.posto))
        .where(Indisp.user_id.in_(user_ids), Indisp.date_end >= date_ini)
    )
    indisps_result = await session.scalars(indisp_query)

    # 4. Agrupa as indisponibilidades por user_id em um dicionário para
    # acesso rápido
    indisps_by_user = defaultdict(list)
    for indisp in indisps_result:
        indisps_by_user[indisp.user_id].append(
            IndispOut.model_validate(indisp)
        )

    # 5. Monta a resposta final
    response = []
    for trip in tripulantes:
        # Pega as indisponibilidades do dicionário
        user_indisps = indisps_by_user.get(trip.user_id, [])
        user_indisps.sort(key=lambda i: i.date_end, reverse=True)

        func_schema = (
            BaseFunc.model_validate(trip.funcs[0]) if trip.funcs else None
        )

        response.append({
            'trip': {
                'trig': trip.trig,
                'id': trip.id,
                'user': UserPublic.model_validate(trip.user),
                'func': func_schema,
            },
            'indisps': user_indisps,
        })

    return response


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_indisp(
    indisp: IndispSchema,
    session: Session,
    user: User = Depends(get_current_user),
):
    if indisp.date_end < indisp.date_start:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data Fim deve ser maior ou igual a data início',
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
    await session.commit()

    return {'detail': 'Indisponibilidade adicionada com sucesso'}


@router.get('/user/{id}', response_model=list[IndispOut])
async def get_indisp_user(
    id: int,
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    mtv: str | None = None,
):
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

    return indisps


@router.delete('/{id}')
async def delete_indisp(
    id: int,
    session: Session,
    user: User = Depends(get_current_user),
):
    indisp = await session.scalar(select(Indisp).where(Indisp.id == id))

    if not indisp:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Indisponibilidade not found',
        )

    # Soft delete - setar deleted_at
    indisp.deleted_at = datetime.now(timezone.utc)

    # Log de deleção
    await log_user_action(
        session=session,
        user_id=user.id,
        action='delete',
        resource='indisp',
        resource_id=indisp.id,
    )

    await session.commit()

    return {'detail': 'Indisponibilidade deletada'}


@router.put('/{id}')
async def update_indisp(
    id: int,
    indisp: BaseIndisp,
    session: Session,
    user: User = Depends(get_current_user),
):
    db_indisp = await session.scalar(select(Indisp).where(Indisp.id == id))

    if not db_indisp:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Indisp not found'
        )

    # Usa valores do payload ou mantém os existentes
    # para verificação de duplicata
    check_date_start = (
        indisp.date_start
        if indisp.date_start is not None
        else db_indisp.date_start
    )
    check_date_end = (
        indisp.date_end if indisp.date_end is not None else db_indisp.date_end
    )
    check_mtv = indisp.mtv if indisp.mtv is not None else db_indisp.mtv
    check_obs = indisp.obs if indisp.obs is not None else db_indisp.obs

    ss_indisp = await session.scalar(
        select(Indisp).where(
            (Indisp.user_id == db_indisp.user_id)
            & (Indisp.date_start == check_date_start)
            & (Indisp.date_end == check_date_end)
            & (Indisp.mtv == check_mtv)
            & (Indisp.obs == check_obs)
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
    for key, value in indisp.model_dump(exclude_unset=True).items():
        if value is None:  # Ignora campos não enviados
            continue
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
        resource='indisp',
        resource_id=db_indisp.id,
        before=before,
        after=after,
    )

    await session.commit()

    return {'detail': 'Indisponibilidade atualizada'}
