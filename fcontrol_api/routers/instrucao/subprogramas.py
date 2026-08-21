from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.instrucao.subprogramas import (
    PaopSubprograma,
    Subprograma,
)
from fcontrol_api.models.shared.funcoes import Funcao, FuncaoUae
from fcontrol_api.schemas.instrucao.subprogramas import (
    SubprogramaCreate,
    SubprogramaOut,
    SubprogramaUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/subprogramas', tags=['Instrucao'])

ViewSubprograma = Depends(permission_checker('instrucao.subprogramas', 'view'))
CreateSubprograma = Depends(
    permission_checker('instrucao.subprogramas', 'create')
)
UpdateSubprograma = Depends(
    permission_checker('instrucao.subprogramas', 'update')
)
DeleteSubprograma = Depends(
    permission_checker('instrucao.subprogramas', 'delete')
)


@router.get(
    '/',
    response_model=ApiResponse[list[SubprogramaOut]],
    dependencies=[ViewSubprograma],
)
async def list_subprogramas(session: Session, active_org: ActiveOrg):
    """Lista os subprogramas de instrucao da organizacao ativa."""
    subprogramas = (
        await session.scalars(
            select(Subprograma)
            .where(Subprograma.uae == active_org)
            .order_by(Subprograma.codigo)
        )
    ).all()

    return success_response(data=list(subprogramas))


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[SubprogramaOut],
    dependencies=[CreateSubprograma],
)
async def create_subprograma(
    dados: SubprogramaCreate,
    session: Session,
    active_org: ActiveOrg,
):
    """Cadastra um subprograma para a organizacao ativa."""
    duplicado = await session.scalar(
        select(Subprograma.id).where(
            Subprograma.uae == active_org,
            Subprograma.codigo == dados.codigo,
        )
    )
    if duplicado:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Código já cadastrado nesta organização',
        )

    # `func` é FK para `funcoes.cod`, mas o conjunto válido é o que a unidade
    # opera (funcoes_uae) — mesmo racional do tripulante. Função esporádica
    # (mestre de lançamento, médico) fica de fora: não tem programa de
    # instrução próprio.
    func_autorizada = await session.scalar(
        select(FuncaoUae.id)
        .join(Funcao, Funcao.cod == FuncaoUae.func_cod)
        .where(
            FuncaoUae.uae == active_org,
            FuncaoUae.func_cod == dados.func,
            FuncaoUae.active.is_(True),
            Funcao.esporadica.is_(False),
        )
    )
    if not func_autorizada:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Função não operada pela organização',
        )

    subprograma = Subprograma(
        uae=active_org,
        codigo=dados.codigo,
        descricao=dados.descricao,
        tipo=dados.tipo,
        func=dados.func,
        observacoes=dados.observacoes,
    )
    session.add(subprograma)
    await session.commit()
    await session.refresh(subprograma)

    return success_response(
        data=subprograma,
        message='Subprograma cadastrado com sucesso',
    )


@router.put(
    '/{subprograma_id}',
    response_model=ApiResponse[SubprogramaOut],
    dependencies=[UpdateSubprograma],
)
async def update_subprograma(
    subprograma_id: int,
    dados: SubprogramaUpdate,
    session: Session,
    active_org: ActiveOrg,
):
    """Atualiza um subprograma da organizacao ativa."""
    subprograma = await session.scalar(
        select(Subprograma).where(
            Subprograma.id == subprograma_id,
            Subprograma.uae == active_org,
        )
    )
    if not subprograma:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Subprograma não encontrado',
        )

    duplicado = await session.scalar(
        select(Subprograma.id).where(
            Subprograma.uae == active_org,
            Subprograma.codigo == dados.codigo,
            Subprograma.id != subprograma_id,
        )
    )
    if duplicado:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Código já cadastrado nesta organização',
        )

    func_autorizada = await session.scalar(
        select(FuncaoUae.id)
        .join(Funcao, Funcao.cod == FuncaoUae.func_cod)
        .where(
            FuncaoUae.uae == active_org,
            FuncaoUae.func_cod == dados.func,
            FuncaoUae.active.is_(True),
            Funcao.esporadica.is_(False),
        )
    )
    if not func_autorizada:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Função não operada pela organização',
        )

    subprograma.codigo = dados.codigo
    subprograma.descricao = dados.descricao
    subprograma.tipo = dados.tipo
    subprograma.func = dados.func
    subprograma.observacoes = dados.observacoes

    await session.commit()
    await session.refresh(subprograma)

    return success_response(
        data=subprograma,
        message='Subprograma atualizado com sucesso',
    )


@router.delete(
    '/{subprograma_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteSubprograma],
)
async def delete_subprograma(
    subprograma_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Remove um subprograma que ainda nao entrou em nenhum PAOP."""
    subprograma = await session.scalar(
        select(Subprograma).where(
            Subprograma.id == subprograma_id,
            Subprograma.uae == active_org,
        )
    )
    if not subprograma:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Subprograma não encontrado',
        )

    em_paop = await session.scalar(
        select(sa_func.count(PaopSubprograma.id)).where(
            PaopSubprograma.subprograma_id == subprograma_id
        )
    )
    if em_paop:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Subprograma incluído em PAOP não pode ser removido '
                f'({em_paop} plano(s))'
            ),
        )

    await session.delete(subprograma)
    await session.commit()

    return success_response(message='Subprograma removido com sucesso')
