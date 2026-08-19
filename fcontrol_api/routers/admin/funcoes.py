"""Manutenção do catálogo de funções (admin de sistema).

O catálogo é doutrina comum a todas as unidades — quem escolhe o que
**opera** é cada org, em `PUT /config/funcoes`. O gate
`require_system_admin` vem do grupo `/admin` e não é repetido aqui.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.funcoes import (
    Funcao,
    FuncaoPosicao,
    FuncaoUae,
)
from fcontrol_api.models.shared.quads import QuadsFunc
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.schemas.funcoes import (
    FuncaoCreate,
    FuncaoOut,
    FuncaoPosicoesSet,
    FuncaoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/funcoes', tags=['Admin - Funcoes'])


async def _get_funcao(cod: str, session: AsyncSession) -> Funcao:
    funcao = await session.get(Funcao, cod)
    if not funcao:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Função não encontrada',
        )
    return funcao


@router.get('/', response_model=ApiResponse[list[FuncaoOut]])
async def list_funcoes_catalogo(session: Session):
    """Catálogo completo, inclusive as funções inativas."""
    funcoes = (
        await session.scalars(
            select(Funcao).order_by(Funcao.ordem, Funcao.cod)
        )
    ).all()
    return success_response(
        data=[FuncaoOut.model_validate(f) for f in funcoes]
    )


@router.post(
    '/', response_model=ApiResponse[FuncaoOut], status_code=HTTPStatus.CREATED
)
async def create_funcao(body: FuncaoCreate, session: Session):
    cod = body.cod.lower()
    if await session.get(Funcao, cod):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'Já existe uma função com o código {cod}',
        )

    funcao = Funcao(
        cod=cod,
        nome=body.nome,
        nome_curto=body.nome_curto,
        cor=body.cor,
        ordem=body.ordem,
        esporadica=body.esporadica,
        active=body.active,
    )
    session.add(funcao)
    await session.commit()
    await session.refresh(funcao)

    return success_response(
        data=FuncaoOut.model_validate(funcao),
        message='Função cadastrada com sucesso',
    )


@router.put('/{cod}', response_model=ApiResponse[FuncaoOut])
async def update_funcao(cod: str, body: FuncaoUpdate, session: Session):
    funcao = await _get_funcao(cod, session)

    for campo, valor in body.model_dump().items():
        setattr(funcao, campo, valor)

    await session.commit()
    await session.refresh(funcao)

    return success_response(
        data=FuncaoOut.model_validate(funcao),
        message='Função atualizada com sucesso',
    )


@router.delete('/{cod}', response_model=ApiResponse[None])
async def delete_funcao(cod: str, session: Session):
    """Remove do catálogo. Função em uso não sai — desative-a."""
    funcao = await _get_funcao(cod, session)

    em_uso = await session.scalar(
        select(func.count())
        .select_from(Tripulante)
        .where(Tripulante.func == cod)
    )
    if em_uso:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                f'{em_uso} tripulante(s) ainda usam esta função. '
                'Desative-a em vez de excluir.'
            ),
        )

    orgs = await session.scalar(
        select(func.count())
        .select_from(FuncaoUae)
        .where(FuncaoUae.func_cod == cod)
    )
    if orgs:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'{orgs} unidade(s) ainda operam esta função',
        )

    quadros = await session.scalar(
        select(func.count())
        .select_from(QuadsFunc)
        .where(QuadsFunc.func == cod)
    )
    if quadros:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Função ainda associada a tipos de quadrinho',
        )

    await session.delete(funcao)
    await session.commit()

    return success_response(message='Função removida com sucesso')


@router.put('/{cod}/posicoes', response_model=ApiResponse[FuncaoOut])
async def set_funcao_posicoes(
    cod: str, body: FuncaoPosicoesSet, session: Session
):
    """Substitui o conjunto de posições a bordo da função."""
    funcao = await _get_funcao(cod, session)

    codigos = [p.cod.upper() for p in body.posicoes]
    if len(set(codigos)) != len(codigos):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='Códigos de posição repetidos',
        )

    await session.execute(
        delete(FuncaoPosicao).where(FuncaoPosicao.func_cod == cod)
    )
    session.add_all([
        FuncaoPosicao(
            func_cod=cod,
            cod=posicao.cod.upper(),
            nome=posicao.nome,
            ordem=posicao.ordem,
            tipo=posicao.tipo,
            descricao=posicao.descricao,
        )
        for posicao in body.posicoes
    ])
    await session.commit()
    await session.refresh(funcao)

    return success_response(
        data=FuncaoOut.model_validate(funcao),
        message='Posições a bordo atualizadas',
    )
