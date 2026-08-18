from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.propostas import Cenario, CenarioLinha, Proposta
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.propostas import (
    PropostaCreate,
    PropostaListItem,
    PropostaOut,
    PropostaUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/propostas', tags=['CEGEP'])

# Mesmo recurso RBAC dos comissionamentos: a proposta é simulação sobre o
# mesmo teto e a mesma carteira, não um domínio à parte.
ViewProposta = Depends(permission_checker('comiss', 'view'))
CreateProposta = Depends(permission_checker('comiss', 'create'))
UpdateProposta = Depends(permission_checker('comiss', 'update'))
DeleteProposta = Depends(permission_checker('comiss', 'delete'))

#: Toda proposta nasce com um cenário: o sandbox sempre tem um ativo, e o
#: front assume `cenarios.length >= 1`.
CENARIO_INICIAL = {'nome': 'Cenário A', 'cor': 'sky'}


async def _carregar(
    session: AsyncSession, proposta_id: int, active_org: str
) -> Proposta:
    """Proposta completa da org ativa, ou 404.

    O escopo entra NA QUERY: o gate autoriza a ação, não o alvo — sem o
    `uae` aqui, quem tem a permissão na sua org leria a proposta de outra.
    """
    proposta = await session.scalar(
        select(Proposta)
        .where(Proposta.id == proposta_id, Proposta.uae == active_org)
        .options(selectinload(Proposta.cenarios).selectinload(Cenario.linhas))
    )
    if not proposta:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Proposta não encontrada'
        )
    return proposta


@router.get(
    '/',
    response_model=ApiResponse[list[PropostaListItem]],
    dependencies=[ViewProposta],
)
async def get_propostas(
    session: Session,
    active_org: ActiveOrg,
    ano_ref: int | None = Query(
        None, description='Filtra pelo exercício de referência'
    ),
):
    """Lista as propostas da org, mais recentes primeiro."""
    # `cenarios_count` por subquery escalar: carregar os cenários todos só
    # para contá-los seria trazer a proposta inteira para exibir um número.
    contagem = (
        select(func.count(Cenario.id))
        .where(Cenario.proposta_id == Proposta.id)
        .scalar_subquery()
    )

    query = (
        select(Proposta, contagem.label('cenarios_count'))
        .where(Proposta.uae == active_org)
        .order_by(Proposta.updated_at.desc(), Proposta.id.desc())
    )
    if ano_ref:
        query = query.where(Proposta.ano_ref == ano_ref)

    linhas = (await session.execute(query)).all()

    return success_response(
        data=[
            PropostaListItem(
                id=p.id,
                nome=p.nome,
                ano_ref=p.ano_ref,
                status=p.status,
                cenarios_count=count,
                updated_at=p.updated_at,
            )
            for p, count in linhas
        ]
    )


@router.get(
    '/{proposta_id}',
    response_model=ApiResponse[PropostaOut],
    dependencies=[ViewProposta],
)
async def get_proposta(
    proposta_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Proposta completa (cenários, linhas e o militar de cada linha)."""
    return success_response(
        data=await _carregar(session, proposta_id, active_org)
    )


@router.post(
    '/',
    response_model=ApiResponse[PropostaOut],
    status_code=HTTPStatus.CREATED,
    dependencies=[CreateProposta],
)
async def create_proposta(
    payload: PropostaCreate,
    session: Session,
    active_org: ActiveOrg,
):
    """Cria a proposta já com o primeiro cenário."""
    proposta = Proposta(
        uae=active_org,
        nome=payload.nome.strip(),
        ano_ref=payload.ano_ref,
    )
    proposta.cenarios.append(Cenario(ordem=0, **CENARIO_INICIAL))

    session.add(proposta)
    await session.commit()

    return success_response(
        data=await _carregar(session, proposta.id, active_org),
        message='Proposta criada com sucesso',
    )


@router.put(
    '/{proposta_id}',
    response_model=ApiResponse[PropostaOut],
    dependencies=[UpdateProposta],
)
async def update_proposta(
    proposta_id: int,
    payload: PropostaUpdate,
    session: Session,
    active_org: ActiveOrg,
):
    """Grava o rascunho inteiro: nome, exercício, cenários e linhas.

    Sincroniza em vez de recriar. Apagar tudo e inserir de novo trocaria os
    ids a cada save, e é justamente pelo eco dos ids que o rascunho da tela
    para de tratar registros existentes como novos.
    """
    proposta = await _carregar(session, proposta_id, active_org)

    # Militares de fora da org não entram numa proposta da org: o gate
    # autoriza a ação, o alvo tem que ser conferido aqui.
    user_ids = {
        linha.user_id for cen in payload.cenarios for linha in cen.linhas
    }
    if user_ids:
        validos = set(
            (
                await session.scalars(
                    select(User.id).where(
                        User.id.in_(user_ids), User.unidade == active_org
                    )
                )
            ).all()
        )
        if invalidos := user_ids - validos:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=(
                    'Militar não encontrado na organização ativa: '
                    f'{sorted(invalidos)}'
                ),
            )

    proposta.nome = payload.nome.strip()
    proposta.ano_ref = payload.ano_ref

    cenarios_por_id = {c.id: c for c in proposta.cenarios}
    mantidos: list[Cenario] = []

    for ordem, cen_in in enumerate(payload.cenarios):
        cenario = cenarios_por_id.get(cen_in.id) if cen_in.id else None
        if cenario is None:
            cenario = Cenario(nome=cen_in.nome, cor=cen_in.cor, ordem=ordem)
            proposta.cenarios.append(cenario)
        else:
            cenario.nome = cen_in.nome
            cenario.cor = cen_in.cor
            cenario.ordem = ordem

        _sincronizar_linhas(cenario, cen_in.linhas)
        mantidos.append(cenario)

    # Cenários que sumiram do payload saem junto com as linhas (cascade).
    for cenario in list(proposta.cenarios):
        if cenario not in mantidos:
            proposta.cenarios.remove(cenario)

    # Tocar na mão: o `onupdate` só dispara se alguma coluna de `propostas`
    # mudar, e o trabalho de verdade acontece nos cenários. Sem isto a lista
    # (ordenada por `updated_at`) e o "atualizado em" da tela congelam.
    proposta.updated_at = datetime.now(timezone.utc)

    await session.commit()

    return success_response(
        data=await _carregar(session, proposta_id, active_org),
        message='Proposta salva com sucesso',
    )


def _sincronizar_linhas(cenario: Cenario, linhas_in: list) -> None:
    """Casa as linhas do payload com as do banco, por id."""
    linhas_por_id = {linha.id: linha for linha in cenario.linhas}
    mantidas: list[CenarioLinha] = []

    for linha_in in linhas_in:
        linha = linhas_por_id.get(linha_in.id) if linha_in.id else None
        if linha is None:
            linha = CenarioLinha(
                user_id=linha_in.user_id,
                base_ab=linha_in.base_ab,
                qtd_ab=linha_in.qtd_ab,
                ano_ab=linha_in.ano_ab,
                base_fc=linha_in.base_fc,
                qtd_fc=linha_in.qtd_fc,
                ano_fc=linha_in.ano_fc,
            )
            cenario.linhas.append(linha)
        else:
            linha.user_id = linha_in.user_id
            linha.base_ab = linha_in.base_ab
            linha.qtd_ab = linha_in.qtd_ab
            linha.ano_ab = linha_in.ano_ab
            linha.base_fc = linha_in.base_fc
            linha.qtd_fc = linha_in.qtd_fc
            linha.ano_fc = linha_in.ano_fc
        mantidas.append(linha)

    for linha in list(cenario.linhas):
        if linha not in mantidas:
            cenario.linhas.remove(linha)


@router.delete(
    '/{proposta_id}',
    response_model=ApiResponse[None],
    dependencies=[DeleteProposta],
)
async def delete_proposta(
    proposta_id: int,
    session: Session,
    active_org: ActiveOrg,
):
    """Exclui a proposta (cenários e linhas vão junto, por cascade)."""
    await _carregar(session, proposta_id, active_org)

    await session.execute(
        delete(Proposta).where(
            Proposta.id == proposta_id, Proposta.uae == active_org
        )
    )
    await session.commit()

    return success_response(data=None, message='Proposta excluída')
