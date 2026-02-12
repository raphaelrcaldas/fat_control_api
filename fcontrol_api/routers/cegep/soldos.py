from datetime import date, timedelta
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from fcontrol_api.models.public.posto_grad import PostoGrad, Soldo
from fcontrol_api.schemas.cegep.soldo import (
    SoldoCreate,
    SoldoPublic,
    SoldoStats,
    SoldoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.services.missao import recalcular_custos_missoes
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/soldos', tags=['CEGEP'])


@router.get('/stats', response_model=ApiResponse[SoldoStats])
async def get_soldo_stats(
    session: Session,
    circulo: str | None = Query(None, description='Filtrar por circulo'),
):
    """Retorna estatisticas dos soldos"""
    query = select(
        func.count(Soldo.id),
        func.min(Soldo.valor),
        func.max(Soldo.valor),
    )

    if circulo:
        query = query.join(PostoGrad).where(PostoGrad.circulo == circulo)

    result = await session.execute(query)
    row = result.one()

    return success_response(
        data=SoldoStats(
            total=row[0] or 0,
            min_valor=row[1],
            max_valor=row[2],
        )
    )


@router.get('/', response_model=ApiResponse[list[SoldoPublic]])
async def list_soldos(
    session: Session,
    circulo: str | None = Query(None, description='Filtrar por circulo'),
    active_only: bool = Query(False, description='Apenas soldos vigentes'),
):
    """Lista todos os soldos com filtros opcionais"""
    query = select(Soldo)

    if circulo:
        query = query.join(PostoGrad).where(PostoGrad.circulo == circulo)

    if active_only:
        today = date.today()
        query = query.where(
            and_(
                Soldo.data_inicio <= today,
                or_(Soldo.data_fim.is_(None), Soldo.data_fim >= today),
            )
        )

    query = query.order_by(Soldo.data_inicio.desc())

    result = await session.scalars(query)
    return success_response(data=list(result.all()))


@router.get('/{soldo_id}', response_model=ApiResponse[SoldoPublic])
async def get_soldo(soldo_id: int, session: Session):
    """Busca um soldo por ID"""
    soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    return success_response(data=soldo)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[SoldoPublic],
)
async def create_soldo(soldo: SoldoCreate, session: Session):
    """Cria um novo registro de soldo"""
    if soldo.data_fim and soldo.data_fim <= soldo.data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data inicio',
        )

    posto = await session.scalar(
        select(PostoGrad).where(PostoGrad.short == soldo.pg)
    )

    if not posto:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Posto/Graduacao invalido',
        )

    # Auto-fechar periodo anterior ativo (mesmo pg)
    anterior = await session.scalar(
        select(Soldo).where(
            and_(
                Soldo.pg == soldo.pg,
                Soldo.data_fim.is_(None),
            )
        )
    )

    if anterior:
        nova_data_fim = soldo.data_inicio - timedelta(days=1)
        if nova_data_fim < anterior.data_inicio:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'Novo soldo comeca antes do soldo vigente '
                    f'(inicio: {anterior.data_inicio})'
                ),
            )
        anterior.data_fim = nova_data_fim

    new_soldo = Soldo(
        pg=soldo.pg,
        data_inicio=soldo.data_inicio,
        data_fim=soldo.data_fim,
        valor=soldo.valor,
    )

    session.add(new_soldo)
    await session.flush()

    await recalcular_custos_missoes(
        soldo.data_inicio, soldo.data_fim, session
    )

    await session.commit()
    await session.refresh(new_soldo)

    return success_response(
        data=SoldoPublic.model_validate(new_soldo),
        message='Soldo criado com sucesso',
    )


@router.put('/{soldo_id}', response_model=ApiResponse[SoldoPublic])
async def update_soldo(soldo_id: int, soldo: SoldoUpdate, session: Session):
    """Atualiza um soldo existente"""
    db_soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not db_soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    # Guardar datas originais para recalculo
    old_inicio = db_soldo.data_inicio
    old_fim = db_soldo.data_fim

    update_data = soldo.model_dump(exclude_unset=True)

    # Valida datas
    data_inicio = update_data.get('data_inicio', db_soldo.data_inicio)
    data_fim = update_data.get('data_fim', db_soldo.data_fim)
    if data_fim and data_fim <= data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data inicio',
        )

    if 'pg' in update_data:
        posto = await session.scalar(
            select(PostoGrad).where(
                PostoGrad.short == update_data['pg']
            )
        )
        if not posto:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Posto/Graduacao invalido',
            )

    for key, value in update_data.items():
        setattr(db_soldo, key, value)

    await session.flush()

    # Recalcular com uniao dos periodos (antigo + novo)
    inicio_min = min(old_inicio, data_inicio)
    fins = [f for f in (old_fim, data_fim) if f is not None]
    fim_max = max(fins) if fins else None

    await recalcular_custos_missoes(inicio_min, fim_max, session)

    await session.commit()
    await session.refresh(db_soldo)

    return success_response(
        data=SoldoPublic.model_validate(db_soldo),
        message='Soldo atualizado com sucesso',
    )


@router.delete('/{soldo_id}', response_model=ApiResponse[None])
async def delete_soldo(soldo_id: int, session: Session):
    """Deleta um registro de soldo"""
    db_soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not db_soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    # Verificar se ha missoes com UserFrag sit='g' no periodo
    query_check = (
        select(UserFrag.id)
        .join(FragMis, FragMis.id == UserFrag.frag_id)
        .join(PernoiteFrag, PernoiteFrag.frag_id == FragMis.id)
        .where(
            UserFrag.sit == 'g',
            PernoiteFrag.data_fim >= db_soldo.data_inicio,
        )
    )
    if db_soldo.data_fim is not None:
        query_check = query_check.where(
            PernoiteFrag.data_ini <= db_soldo.data_fim
        )

    missao_vinculada = await session.scalar(query_check.limit(1))
    if missao_vinculada:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Não é possível deletar: existem missões com '
                'gratificação de representação no período '
                'deste soldo'
            ),
        )

    # Guardar datas antes de deletar
    del_inicio = db_soldo.data_inicio
    del_fim = db_soldo.data_fim

    await session.delete(db_soldo)
    await session.flush()

    await recalcular_custos_missoes(del_inicio, del_fim, session)

    await session.commit()

    return success_response(message='Soldo deletado com sucesso')
