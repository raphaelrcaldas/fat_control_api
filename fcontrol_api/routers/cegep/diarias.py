from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.diarias import DiariaValor, GrupoCidade, GrupoPg
from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.models.public.posto_grad import PostoGrad
from fcontrol_api.schemas.diaria import (
    DiariaValorCreate,
    DiariaValorPublic,
    DiariaValorUpdate,
    GrupoCidadePublic,
    GrupoPgPublic,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/diarias', tags=['CEGEP'])


def calculate_status(data_inicio: date, data_fim: date | None) -> str:
    """Calcula status baseado nas datas"""
    today = date.today()
    if data_inicio > today:
        return 'proximo'
    if data_fim and data_fim < today:
        return 'anterior'
    return 'vigente'


@router.get('/valores/', response_model=ApiResponse[list[DiariaValorPublic]])
async def list_diaria_valores(
    session: Session,
    grupo_cid: int | None = Query(
        None, description='Filtrar por grupo de cidade'
    ),
    grupo_pg: int | None = Query(None, description='Filtrar por grupo de P/G'),
    active_only: bool = Query(False, description='Apenas valores vigentes'),
):
    """Lista todos os valores de diárias"""
    query = select(DiariaValor)

    if grupo_cid is not None:
        query = query.where(DiariaValor.grupo_cid == grupo_cid)

    if grupo_pg is not None:
        query = query.where(DiariaValor.grupo_pg == grupo_pg)

    if active_only:
        today = date.today()
        query = query.where(
            and_(
                DiariaValor.data_inicio <= today,
                or_(
                    DiariaValor.data_fim.is_(None),
                    DiariaValor.data_fim >= today,
                ),
            )
        )

    query = query.order_by(
        DiariaValor.grupo_cid,
        DiariaValor.grupo_pg,
        DiariaValor.data_inicio.desc(),
    )

    result = await session.scalars(query)
    valores = result.all()

    # Adiciona status calculado
    return success_response(
        data=[
            DiariaValorPublic(
                id=v.id,
                grupo_pg=v.grupo_pg,
                grupo_cid=v.grupo_cid,
                valor=v.valor,
                data_inicio=v.data_inicio,
                data_fim=v.data_fim,
                status=calculate_status(v.data_inicio, v.data_fim),
            )
            for v in valores
        ]
    )


@router.get(
    '/valores/{valor_id}',
    response_model=ApiResponse[DiariaValorPublic],
)
async def get_diaria_valor(valor_id: int, session: Session):
    """Busca valor de diária por ID"""
    valor = await session.scalar(
        select(DiariaValor).where(DiariaValor.id == valor_id)
    )

    if not valor:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Valor de diária não encontrado',
        )

    return success_response(
        data=DiariaValorPublic(
            id=valor.id,
            grupo_pg=valor.grupo_pg,
            grupo_cid=valor.grupo_cid,
            valor=valor.valor,
            data_inicio=valor.data_inicio,
            data_fim=valor.data_fim,
            status=calculate_status(valor.data_inicio, valor.data_fim),
        )
    )


@router.post(
    '/valores/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[DiariaValorPublic],
)
async def create_diaria_valor(data: DiariaValorCreate, session: Session):
    """Cria um novo valor de diária"""
    if data.data_fim and data.data_fim <= data.data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data início',
        )

    new_valor = DiariaValor(
        grupo_pg=data.grupo_pg,
        grupo_cid=data.grupo_cid,
        valor=data.valor,
        data_inicio=data.data_inicio,
        data_fim=data.data_fim,
    )

    session.add(new_valor)
    await session.commit()
    await session.refresh(new_valor)

    return success_response(
        data=DiariaValorPublic(
            id=new_valor.id,
            grupo_pg=new_valor.grupo_pg,
            grupo_cid=new_valor.grupo_cid,
            valor=new_valor.valor,
            data_inicio=new_valor.data_inicio,
            data_fim=new_valor.data_fim,
            status=calculate_status(new_valor.data_inicio, new_valor.data_fim),
        ),
        message='Valor de diária criado com sucesso',
    )


@router.put(
    '/valores/{valor_id}',
    response_model=ApiResponse[DiariaValorPublic],
)
async def update_diaria_valor(
    valor_id: int, data: DiariaValorUpdate, session: Session
):
    """Atualiza um valor de diária existente"""
    db_valor = await session.scalar(
        select(DiariaValor).where(DiariaValor.id == valor_id)
    )

    if not db_valor:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Valor de diária não encontrado',
        )

    update_data = data.model_dump(exclude_unset=True)

    # Valida datas
    data_inicio = update_data.get('data_inicio', db_valor.data_inicio)
    data_fim = update_data.get('data_fim', db_valor.data_fim)
    if data_fim and data_fim <= data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data início',
        )

    for key, value in update_data.items():
        setattr(db_valor, key, value)

    await session.commit()
    await session.refresh(db_valor)

    return success_response(
        data=DiariaValorPublic(
            id=db_valor.id,
            grupo_pg=db_valor.grupo_pg,
            grupo_cid=db_valor.grupo_cid,
            valor=db_valor.valor,
            data_inicio=db_valor.data_inicio,
            data_fim=db_valor.data_fim,
            status=calculate_status(db_valor.data_inicio, db_valor.data_fim),
        ),
        message='Valor de diária atualizado com sucesso',
    )


@router.delete('/valores/{valor_id}', response_model=ApiResponse[None])
async def delete_diaria_valor(valor_id: int, session: Session):
    """Deleta um valor de diária"""
    db_valor = await session.scalar(
        select(DiariaValor).where(DiariaValor.id == valor_id)
    )

    if not db_valor:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Valor de diária não encontrado',
        )

    await session.delete(db_valor)
    await session.commit()

    return success_response(message='Valor de diária deletado com sucesso')


@router.get(
    '/grupos-cidade/',
    response_model=ApiResponse[list[GrupoCidadePublic]],
)
async def list_grupos_cidade(session: Session):
    """Lista todos os grupos de cidade com cidades associadas"""
    query = (
        select(GrupoCidade, Cidade)
        .join(Cidade, GrupoCidade.cidade_id == Cidade.codigo)
        .order_by(GrupoCidade.grupo, Cidade.nome)
    )

    result = await session.execute(query)
    rows = result.all()

    return success_response(
        data=[
            GrupoCidadePublic(
                id=gc.id,
                grupo=gc.grupo,
                cidade_id=gc.cidade_id,
                cidade={
                    'codigo': cidade.codigo,
                    'nome': cidade.nome,
                    'uf': cidade.uf,
                }
                if cidade
                else None,
            )
            for gc, cidade in rows
        ]
    )


@router.get('/grupos-pg/', response_model=ApiResponse[list[GrupoPgPublic]])
async def list_grupos_pg(session: Session):
    """Lista todos os grupos de posto/graduação"""
    query = (
        select(GrupoPg, PostoGrad)
        .join(PostoGrad, GrupoPg.pg_short == PostoGrad.short)
        .order_by(GrupoPg.grupo, PostoGrad.ant)
    )

    result = await session.execute(query)
    rows = result.all()

    return success_response(
        data=[
            GrupoPgPublic(
                id=gpg.id,
                grupo=gpg.grupo,
                pg_short=gpg.pg_short,
                pg_mid=pg.mid if pg else None,
                pg_long=pg.long if pg else None,
                circulo=pg.circulo if pg else None,
            )
            for gpg, pg in rows
        ]
    )
