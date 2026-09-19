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

from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.gle import MilitarGle, MissaoGle, TrechoGle
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.gle_missao import (
    MilitarMissaoOut,
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
from fcontrol_api.services.gle_apuracao import (
    ROTULO_PERCENTUAL,
    MilitarApurar,
    TrechoApurar,
    apurar,
    carregar_localidades,
)
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


def _snapshot(missao: MissaoGle) -> dict:
    """Estado JSON-serializável da missão para auditoria.

    Lê somente escalares e coleções que já estejam em memória. O chamador
    precisa garantir que `trechos` e `militares` foram carregados para não
    disparar lazy-load fora do contexto greenlet.
    """
    trechos = [
        {
            'loc_esp_id': trecho.loc_esp_id,
            'chegada': trecho.chegada.isoformat(),
            'afastamento': trecho.afastamento.isoformat(),
        }
        for trecho in sorted(
            missao.trechos,
            key=lambda item: (
                item.loc_esp_id,
                item.chegada,
                item.afastamento,
            ),
        )
    ]
    militares = [
        {'user_id': militar.user_id, 'p_g': militar.p_g}
        for militar in sorted(
            missao.militares,
            key=lambda item: (item.user_id, item.p_g),
        )
    ]
    return {
        'descricao': missao.descricao,
        'obs': missao.obs,
        'trechos': trechos,
        'militares': militares,
    }


async def _buscar_missao(
    session: AsyncSession, missao_id: int, active_org: str
) -> MissaoGle:
    """Missão da org ativa, ou 404.

    O filtro por `uae` está aqui e não no handler para que nenhuma rota
    esqueça dele. Missão de outra unidade responde 404, não 403: a
    existência dela não é informação a dar.
    """
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
    return missao


async def _carregar_militares(
    session: AsyncSession, ids: list[int], active_org: str
) -> list[User]:
    """Militares da própria unidade.

    O id vem do corpo da requisição e o gate autoriza a **ação**, não o
    alvo: sem `User.unidade == active_org`, um id de outra unidade entraria
    na missão e o GET seguinte devolveria nome e SARAM daquele militar. A
    recusa é neutra de propósito.
    """
    if not ids:
        return []
    users = (
        await session.scalars(
            select(User).where(User.id.in_(ids), User.unidade == active_org)
        )
    ).all()
    achados = {u.id for u in users}
    ausentes = sorted(set(ids) - achados)
    if ausentes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Militar não encontrado: '
                + ', '.join(str(i) for i in ausentes)
            ),
        )
    return list(users)


async def _montar_out(
    session: AsyncSession, missao: MissaoGle
) -> MissaoGleOut:
    """Recalcula a missão salva e devolve a apuração completa."""
    ids_locs = {t.loc_esp_id for t in missao.trechos}
    por_id = await carregar_localidades(session, ids_locs)

    # Localidade apagada depois de a missão ser salva: o FK é RESTRICT, mas
    # a defesa fica porque o `_montar_out` também serve a dado antigo.
    faltantes = sorted(ids_locs - por_id.keys())
    if faltantes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Localidade especial da missão não existe mais: '
                + ', '.join(str(i) for i in faltantes)
            ),
        )

    # `p_g` gravado, não o atual: promover alguém não reescreve a apuração.
    militares = sorted(
        missao.militares,
        key=lambda m: (
            m.user.posto.ant,
            m.user.ult_promo or date.min,
            m.user.ant_rel or 0,
        ),
    )
    apuracao = await apurar(
        session,
        [
            TrechoApurar(t.loc_esp_id, t.chegada, t.afastamento)
            for t in missao.trechos
        ],
        [
            MilitarApurar(
                m.user_id,
                m.p_g,
                m.user.nome_guerra,
                m.user.nome_completo,
                m.user.saram,
            )
            for m in militares
        ],
        por_id,
    )
    por_user = {uid: (soldo, valor) for uid, soldo, valor in apuracao.valores}

    return MissaoGleOut(
        id=missao.id,
        descricao=missao.descricao,
        obs=missao.obs,
        created_at=missao.created_at,
        multiplicador=apuracao.multiplicador,
        percentual=apuracao.percentual,
        trechos=apuracao.trechos,
        militares=[
            MilitarMissaoOut(
                user_id=m.user_id,
                p_g=m.p_g,
                nome_guerra=m.user.nome_guerra,
                nome_completo=m.user.nome_completo,
                saram=m.user.saram,
                soldo=por_user[m.user_id][0],
                valor=por_user[m.user_id][1],
            )
            for m in militares
        ],
    )


async def _aplicar_conteudo(
    session: AsyncSession,
    missao: MissaoGle,
    payload: MissaoGleCreate | MissaoGleUpdate,
    active_org: str,
) -> None:
    """Substitui trechos e militares da missão pelos informados."""
    ids_locs = {t.loc_esp_id for t in payload.trechos}
    por_id = await carregar_localidades(session, ids_locs)
    faltantes = sorted(ids_locs - por_id.keys())
    if faltantes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Localidade especial não encontrada: '
                + ', '.join(str(i) for i in faltantes)
            ),
        )

    users = await _carregar_militares(
        session, payload.militares_ids, active_org
    )
    # Posto atual de quem entra agora; quem já estava preserva o snapshot.
    ja_gravados = {m.user_id: m.p_g for m in missao.militares}

    # Esvazia e dá `flush` ANTES de reinserir: na mesma descarga, o
    # SQLAlchemy emite o INSERT das novas linhas antes do DELETE das
    # antigas e `uq_militar_gle_missao_user` estoura quando o mesmo militar
    # permanece na missão.
    missao.trechos.clear()
    missao.militares.clear()
    await session.flush()

    missao.trechos = [
        TrechoGle(
            loc_esp_id=t.loc_esp_id,
            chegada=t.chegada,
            afastamento=t.afastamento,
        )
        for t in payload.trechos
    ]
    missao.militares = [
        MilitarGle(
            user_id=u.id,
            p_g=ja_gravados.get(u.id, u.p_g),
        )
        for u in users
    ]


@router.get(
    '',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[MissaoGleResumo]],
    dependencies=[ViewGle],
)
async def listar_missoes(session: Session, active_org: ActiveOrg):
    """Missões da organização ativa, da mais recente para a mais antiga."""
    missoes = (
        await session.scalars(
            select(MissaoGle)
            .where(MissaoGle.uae == active_org)
            .order_by(MissaoGle.created_at.desc(), MissaoGle.id.desc())
        )
    ).all()

    ids_locs = {t.loc_esp_id for m in missoes for t in m.trechos}
    por_id = await carregar_localidades(session, ids_locs)

    resumos: list[MissaoGleResumo] = []
    for missao in missoes:
        datas = [t.chegada for t in missao.trechos]
        fins = [t.afastamento for t in missao.trechos]
        grupos = {
            por_id[t.loc_esp_id][0].grupo
            for t in missao.trechos
            if t.loc_esp_id in por_id
        }
        # Nomes sem repetir e em ordem: a lista serve para reconhecer a
        # missão de relance, não para detalhar.
        cidades = sorted({
            f'{por_id[t.loc_esp_id][1].nome} - {por_id[t.loc_esp_id][1].uf}'
            for t in missao.trechos
            if t.loc_esp_id in por_id
        })
        resumos.append(
            MissaoGleResumo(
                id=missao.id,
                descricao=missao.descricao,
                created_at=missao.created_at,
                total_trechos=len(missao.trechos),
                total_militares=len(missao.militares),
                percentual=' e '.join(
                    ROTULO_PERCENTUAL[g] for g in sorted(grupos)
                ),
                primeira_data=min(datas),
                ultima_data=max(fins),
                localidades=cidades,
            )
        )

    return success_response(data=resumos)


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
):
    missao = MissaoGle(descricao=payload.descricao, obs=payload.obs)
    missao.uae = active_org
    session.add(missao)
    await _aplicar_conteudo(session, missao, payload, active_org)
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
    return success_response(data=await _montar_out(session, missao))


@router.get(
    '/{missao_id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MissaoGleOut],
    dependencies=[ViewGle],
)
async def obter_missao(
    missao_id: MissaoId, session: Session, active_org: ActiveOrg
):
    missao = await _buscar_missao(session, missao_id, active_org)
    return success_response(data=await _montar_out(session, missao))


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
):
    missao = await _buscar_missao(session, missao_id, active_org)

    antes = _snapshot(missao)

    missao.descricao = payload.descricao
    missao.obs = payload.obs
    await _aplicar_conteudo(session, missao, payload, active_org)
    await session.flush()

    depois = _snapshot(missao)
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
    return success_response(data=await _montar_out(session, missao))


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
):
    missao = await _buscar_missao(session, missao_id, active_org)
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
