from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.cegep.comiss import ComissSchema
from fcontrol_api.schemas.cegep.missoes import FragMisSchema
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.services.comis import verificar_conflito_comiss
from fcontrol_api.utils.financeiro import custo_missao
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/comiss', tags=['CEGEP'])


@router.get('/', response_model=ApiResponse[list])
async def get_cmtos(
    session: Session,
    user_id: int = None,
    status: str = None,
    search: str = None,
):
    """
    Lista comissionamentos com valores pré-calculados do cache.
    Não retorna missões - use GET /{comiss_id} para detalhes.
    """
    query = (
        select(Comissionamento)
        .join(User)
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

    result = await session.scalars(query)
    comiss_list = result.all()

    response = []
    for comiss in comiss_list:
        user = UserPublic.model_validate(comiss.user).model_dump()
        comiss_data = ComissSchema.model_validate(comiss).model_dump(
            exclude={'user_id'},
        )
        comiss_data['user'] = user

        # Ler valores do cache JSONB
        cache = comiss.cache_calc or {}
        comiss_data['dias_comp'] = cache.get('dias_comp', 0)
        comiss_data['diarias_comp'] = cache.get('diarias_comp', 0)
        comiss_data['vals_comp'] = cache.get('vals_comp', 0)
        comiss_data['modulo'] = cache.get('modulo', False)
        comiss_data['completude'] = cache.get('completude', 0)
        comiss_data['missoes_count'] = cache.get('missoes_count', 0)

        response.append(comiss_data)

    return success_response(data=response)


@router.get('/{comiss_id}', response_model=ApiResponse[dict])
async def get_cmto_by_id(
    comiss_id: int,
    session: Session,
):
    """
    Retorna um comissionamento com todas as missões agregadas.
    """
    comiss = await session.scalar(
        select(Comissionamento).where(Comissionamento.id == comiss_id)
    )

    if not comiss:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Comissionamento não encontrado',
        )

    # Montar dados base
    user = UserPublic.model_validate(comiss.user).model_dump()
    comiss_data = ComissSchema.model_validate(comiss).model_dump(
        exclude={'user_id'},
    )
    comiss_data['user'] = user

    # Ler valores do cache JSONB
    cache = comiss.cache_calc or {}
    comiss_data['dias_comp'] = cache.get('dias_comp', 0)
    comiss_data['diarias_comp'] = cache.get('diarias_comp', 0)
    comiss_data['vals_comp'] = cache.get('vals_comp', 0)
    comiss_data['modulo'] = cache.get('modulo', False)
    comiss_data['completude'] = cache.get('completude', 0)

    # Buscar missões do comissionamento
    query = (
        select(FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == comiss.user_id,
                UserFrag.sit == 'c',
                UserFrag.frag_id == FragMis.id,
            ),
        )
        .where(
            and_(
                FragMis.afast >= comiss.data_ab,
                FragMis.regres <= comiss.data_fc,
            )
        )
        .order_by(FragMis.afast)
    )

    result = await session.execute(query)
    registros = result.all()

    missoes = []
    for missao, user_frag in registros:
        missao_data = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )
        missao_data = custo_missao(
            user_frag.p_g,
            user_frag.sit,
            missao_data,
        )
        missoes.append(missao_data)

    comiss_data['missoes'] = missoes

    return success_response(data=comiss_data)


@router.post('/', response_model=ApiResponse[None])
async def create_cmto(
    session: Session,
    comiss: ComissSchema,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            (Comissionamento.user_id == comiss.user_id)
            & (Comissionamento.status == 'aberto')
        )
    )
    if db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Já existe um comissionamento aberto para este usuário.',
        )

    await verificar_conflito_comiss(
        comiss.user_id, comiss.data_ab, comiss.data_fc, session
    )

    comiss_data = ComissSchema.model_validate(comiss).model_dump(
        exclude={'id'}
    )
    new_comiss = Comissionamento(**comiss_data)

    session.add(new_comiss)

    await session.commit()

    return success_response(message='Comissionamento criado com sucesso')


@router.put('/{comiss_id}', response_model=ApiResponse[None])
async def update_cmto(
    comiss_id: int,
    session: Session,
    comiss: ComissSchema,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where((Comissionamento.id == comiss_id))
    )

    if not db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento não encontrado',
        )

    await verificar_conflito_comiss(
        comiss.user_id, comiss.data_ab, comiss.data_fc, session, comiss_id
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
                FragMis.afast >= Comissionamento.data_ab,
                FragMis.regres <= Comissionamento.data_fc,
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
                FragMis.afast >= comiss.data_ab,
                FragMis.regres <= comiss.data_fc,
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

    for key, value in comiss.model_dump(exclude_unset=True).items():
        setattr(db_comiss, key, value)

    await session.commit()
    await session.refresh(db_comiss)

    return success_response(message='Comissionamento atualizado com sucesso')


@router.delete('/{comiss_id}', response_model=ApiResponse[None])
async def delete_cmto(
    comiss_id: int,
    session: Session,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where((Comissionamento.id == comiss_id))
    )

    if not db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento não encontrado',
        )

    comiss_missoes = await session.scalar(
        select(Comissionamento, FragMis, UserFrag)
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
                FragMis.afast >= Comissionamento.data_ab,
                FragMis.regres <= Comissionamento.data_fc,
            ),
        )
        .where(Comissionamento.id == comiss_id)
    )

    if comiss_missoes:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=('Existem missões atribuidas a este comissionamento',),
        )

    await session.delete(db_comiss)
    await session.commit()

    return success_response(message='Comissionamento deletado')
