"""Missões de GLE — os trabalhos salvos da apuração.

**Escopado por organização**, ao contrário do cadastro de localidades: a
apuração é trabalho de pessoal da unidade, e nomeia militares e valores.
Todo acesso filtra por `MissaoGle.uae == active_org`, e o write-path valida
também o **alvo** (o militar informado tem de ser da própria unidade), não
só a ação — ver `docs/ai/notes/dominio.md`.

O valor **não é gravado**: é recalculado a cada leitura a partir dos
trechos, do soldo vigente e da classificação da localidade. Gravá-lo faria
a missão mentir no dia em que o soldo fosse corrigido.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.gle import MissaoGle
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.gle_missao import (
    MissaoGleCreate,
    MissaoGleOut,
    MissaoGleResumo,
    MissaoGleUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    ActiveOrg,
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.gle.auditoria import snapshot_missao
from fcontrol_api.services.gle.leitura import montar_missao, resumir_missoes
from fcontrol_api.services.gle.missoes import aplicar_conteudo
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
MissaoId = Annotated[int, Path()]

router = APIRouter(prefix='/gle/missoes', tags=['CEGEP'])

RESOURCE = 'missao_gle'

ViewGle = Depends(permission_checker('cegep.gle', 'view'))
CreateGle = Depends(permission_checker('cegep.gle', 'create'))
UpdateGle = Depends(permission_checker('cegep.gle', 'update'))
DeleteGle = Depends(permission_checker('cegep.gle', 'delete'))


@router.get(
    '',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[MissaoGleResumo]],
    dependencies=[ViewGle],
)
async def listar_missoes(
    session: Session, active_org: ActiveOrg
) -> ApiResponse[list[MissaoGleResumo]]:
    """Missões da organização ativa, da mais recente para a mais antiga."""
    missoes = (
        await session.scalars(
            select(MissaoGle)
            .where(MissaoGle.uae == active_org)
            .order_by(MissaoGle.created_at.desc(), MissaoGle.id.desc())
        )
    ).all()

    return success_response(data=await resumir_missoes(session, missoes))


@router.post(
    '',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[MissaoGleOut],
    dependencies=[CreateGle],
)
async def criar_missao(
    payload: MissaoGleCreate,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
) -> ApiResponse[MissaoGleOut]:
    missao = MissaoGle(descricao=payload.descricao, obs=payload.obs)
    missao.uae = active_org
    session.add(missao)
    users = (
        await session.scalars(
            select(User).where(
                User.id.in_(payload.militares_ids),
                User.unidade == active_org,
            )
        )
    ).all()
    await aplicar_conteudo(session, missao, payload, users)
    await session.flush()

    await log_user_action(
        session,
        current_user.id,
        'create',
        RESOURCE,
        missao.id,
        after={
            'descricao': missao.descricao,
            'trechos': len(missao.trechos),
            'militares': len(missao.militares),
        },
    )
    await session.commit()
    await session.refresh(missao)
    return success_response(data=await montar_missao(session, missao))


@router.get(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoGleOut],
    dependencies=[ViewGle],
)
async def obter_missao(
    missao_id: MissaoId, session: Session, active_org: ActiveOrg
) -> ApiResponse[MissaoGleOut]:
    missao = await session.scalar(
        select(MissaoGle).where(
            MissaoGle.id == missao_id, MissaoGle.uae == active_org
        )
    )
    if missao is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada.',
        )
    return success_response(data=await montar_missao(session, missao))


@router.put(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoGleOut],
    dependencies=[UpdateGle],
)
async def atualizar_missao(
    missao_id: MissaoId,
    payload: MissaoGleUpdate,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
) -> ApiResponse[MissaoGleOut]:
    missao = await session.scalar(
        select(MissaoGle).where(
            MissaoGle.id == missao_id, MissaoGle.uae == active_org
        )
    )
    if missao is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada.',
        )

    antes = snapshot_missao(missao)

    missao.descricao = payload.descricao
    missao.obs = payload.obs
    users = (
        await session.scalars(
            select(User).where(
                User.id.in_(payload.militares_ids),
                User.unidade == active_org,
            )
        )
    ).all()
    await aplicar_conteudo(session, missao, payload, users)
    await session.flush()

    depois = snapshot_missao(missao)
    if antes != depois:
        await log_user_action(
            session,
            current_user.id,
            'update',
            RESOURCE,
            missao.id,
            before=antes,
            after=depois,
        )
    await session.commit()
    await session.refresh(missao)
    return success_response(data=await montar_missao(session, missao))


@router.delete(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
    dependencies=[DeleteGle],
)
async def remover_missao(
    missao_id: MissaoId,
    session: Session,
    current_user: CurrentUser,
    active_org: ActiveOrg,
) -> ApiResponse[None]:
    missao = await session.scalar(
        select(MissaoGle).where(
            MissaoGle.id == missao_id, MissaoGle.uae == active_org
        )
    )
    if missao is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Missão não encontrada.',
        )
    await log_user_action(
        session,
        current_user.id,
        'delete',
        RESOURCE,
        missao.id,
        before={'descricao': missao.descricao},
    )
    # Trechos e militares somem pelo cascade; a localidade e o militar em
    # si, não (FK RESTRICT).
    await session.delete(missao)
    await session.commit()
    return success_response(data=None, message='Missão removida.')
