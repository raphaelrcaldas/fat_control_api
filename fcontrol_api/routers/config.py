"""Configurações da própria organização (geridas pelo admin do tenant).

Diferente de `/admin/*` e de `/tenants` (escopo de sistema), aqui a org é
sempre a **ativa do token** — não há `organizacao_id` no path. Isso é
deliberado: com `require_admin` (admin *na org ativa*), um path param abriria
IDOR cross-org, já que o gate autoriza a ação, não o alvo. Sem o param, o
admin do 11gt não tem como escrever na config do 12gt.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.enums.cargo import CargoEnum
from fcontrol_api.models.shared.funcoes import Funcao, FuncaoUae
from fcontrol_api.models.shared.tenant import TenantCargo
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.funcoes import (
    FuncaoOrgOut,
    FuncaoPosicaoOut,
    FuncoesOrgSet,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.schemas.tenant import TenantCargoOut, TenantCargoUpsert
from fcontrol_api.security import ActiveOrg, require_admin
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/config', tags=['config'])

Session = Annotated[AsyncSession, Depends(get_session)]


# Leitura sem gate de admin: quem exporta a Ordem de Missão é usuário de
# operações e precisa dos titulares para montar o rodapé de assinaturas —
# que é justamente o que sai impresso no documento. A org ativa já limita o
# alcance. Escrever, sim, exige admin da org.
@router.get('/cargos', response_model=ApiResponse[list[TenantCargoOut]])
async def list_cargos(session: Session, active_org: ActiveOrg):
    cargos = await session.scalars(
        select(TenantCargo)
        .where(TenantCargo.uae == active_org)
        .order_by(TenantCargo.cargo)
    )
    return success_response(
        data=[TenantCargoOut.model_validate(c) for c in cargos]
    )


@router.put(
    '/cargos/{cargo}',
    response_model=ApiResponse[TenantCargoOut],
    dependencies=[Depends(require_admin)],
)
async def set_cargo(
    cargo: CargoEnum,
    body: TenantCargoUpsert,
    session: Session,
    active_org: ActiveOrg,
):
    """Define o titular do cargo (idempotente: cria ou troca o titular)."""
    user = await session.get(User, body.user_id)
    if not user:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Usuário não encontrado',
        )
    # O titular assina em nome da org: tem de ser efetivo dela. Sem isso, um
    # militar de outra unidade poderia acabar no rodapé do documento.
    if user.unidade != active_org:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Usuário não pertence a esta organização',
        )
    if not user.active:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Usuário inativo não pode ocupar um cargo',
        )
    # `nome_completo` é nullable no cadastro, mas é justamente o que sai
    # impresso na linha de assinatura — sem ele o documento sairia assinado
    # pelo nome de guerra. Exigir aqui evita o documento defeituoso.
    if not user.nome_completo:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                'Titular precisa ter o nome completo cadastrado para '
                'assinar documentos'
            ),
        )

    vinculo = await session.scalar(
        select(TenantCargo).where(
            TenantCargo.uae == active_org,
            TenantCargo.cargo == cargo.value,
        )
    )
    if vinculo:
        vinculo.user_id = body.user_id
    else:
        vinculo = TenantCargo(
            uae=active_org, cargo=cargo.value, user_id=body.user_id
        )
        session.add(vinculo)

    await session.commit()
    await session.refresh(vinculo)
    return success_response(
        data=TenantCargoOut.model_validate(vinculo),
        message='Titular do cargo definido com sucesso',
    )


@router.delete(
    '/cargos/{cargo}',
    response_model=ApiResponse[None],
    dependencies=[Depends(require_admin)],
)
async def remove_cargo(
    cargo: CargoEnum, session: Session, active_org: ActiveOrg
):
    vinculo = await session.scalar(
        select(TenantCargo).where(
            TenantCargo.uae == active_org,
            TenantCargo.cargo == cargo.value,
        )
    )
    if not vinculo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Cargo não atribuído nesta organização',
        )

    await session.delete(vinculo)
    await session.commit()
    return success_response(message='Titular do cargo removido com sucesso')


# =============================================================================
# FUNÇÕES OPERADAS PELA UNIDADE
# =============================================================================

# Leitura sem gate de admin pelo mesmo motivo dos cargos: o cadastro de
# tripulante, a escala e os quadros precisam saber quais funções a unidade
# opera para montar seus seletores. Definir o conjunto, sim, exige admin.


def _funcao_org_out(vinculo: FuncaoUae) -> FuncaoOrgOut:
    """Projeta a função com o rótulo e a ordem efetivos da org."""
    catalogo = vinculo.funcao
    return FuncaoOrgOut(
        cod=catalogo.cod,
        nome=vinculo.nome_custom or catalogo.nome,
        nome_curto=catalogo.nome_curto,
        cor=catalogo.cor,
        ordem=vinculo.ordem if vinculo.ordem is not None else catalogo.ordem,
        esporadica=catalogo.esporadica,
        posicoes=[
            FuncaoPosicaoOut.model_validate(p) for p in catalogo.posicoes
        ],
    )


@router.get('/funcoes', response_model=ApiResponse[list[FuncaoOrgOut]])
async def list_funcoes_org(session: Session, active_org: ActiveOrg):
    """Funções que a org ativa opera, já com rótulo e ordem efetivos."""
    vinculos = await session.scalars(
        select(FuncaoUae).where(
            FuncaoUae.uae == active_org,
            FuncaoUae.active.is_(True),
        )
    )

    itens = [_funcao_org_out(v) for v in vinculos]
    itens.sort(key=lambda f: (f.ordem, f.cod))

    return success_response(data=itens)


@router.put(
    '/funcoes',
    response_model=ApiResponse[list[FuncaoOrgOut]],
    dependencies=[Depends(require_admin)],
)
async def set_funcoes_org(
    body: FuncoesOrgSet, session: Session, active_org: ActiveOrg
):
    """Define o conjunto de funções operadas pela org (substitui o atual)."""
    codigos = [item.cod.lower() for item in body.funcoes]
    if len(set(codigos)) != len(codigos):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='Função repetida na lista',
        )

    catalogo = {
        f.cod
        for f in await session.scalars(
            select(Funcao).where(
                Funcao.cod.in_(codigos), Funcao.active.is_(True)
            )
        )
    }
    desconhecidas = [cod for cod in codigos if cod not in catalogo]
    if desconhecidas:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f'Função inexistente no catálogo: {", ".join(desconhecidas)}'
            ),
        )

    atuais = {
        v.func_cod: v
        for v in await session.scalars(
            select(FuncaoUae).where(FuncaoUae.uae == active_org)
        )
    }

    # Remover função que ainda tem tripulante ativo deixaria o cadastro
    # apontando para algo que a unidade "não opera" — e o seletor da tela
    # não teria como exibi-la de volta.
    removidas = [cod for cod in atuais if cod not in codigos]
    if removidas:
        em_uso = (
            await session.execute(
                select(Tripulante.func, func.count())
                .where(
                    Tripulante.uae == active_org,
                    Tripulante.active.is_(True),
                    Tripulante.func.in_(removidas),
                )
                .group_by(Tripulante.func)
            )
        ).all()
        if em_uso:
            detalhe = ', '.join(f'{cod} ({total})' for cod, total in em_uso)
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=(
                    'Função com tripulante ativo não pode ser removida: '
                    f'{detalhe}'
                ),
            )

        for cod in removidas:
            await session.delete(atuais[cod])

    for item in body.funcoes:
        cod = item.cod.lower()
        vinculo = atuais.get(cod)
        if vinculo:
            vinculo.nome_custom = item.nome_custom
            vinculo.ordem = item.ordem
            vinculo.active = True
        else:
            session.add(
                FuncaoUae(
                    uae=active_org,
                    func_cod=cod,
                    nome_custom=item.nome_custom,
                    ordem=item.ordem,
                )
            )

    await session.commit()

    vinculos = await session.scalars(
        select(FuncaoUae).where(
            FuncaoUae.uae == active_org,
            FuncaoUae.active.is_(True),
        )
    )
    itens = [_funcao_org_out(v) for v in vinculos]
    itens.sort(key=lambda f: (f.ordem, f.cod))

    return success_response(
        data=itens, message='Funções da unidade atualizadas'
    )
