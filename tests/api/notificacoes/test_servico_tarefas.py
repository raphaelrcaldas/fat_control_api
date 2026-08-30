"""Dedupe e resolução das tarefas compartilhadas (nível de serviço).

Nada emite tarefa na v1, então estas são as únicas provas de que
`abrir_tarefa`/`resolver_tarefas` funcionam. O ponto crítico é o
`on_conflict_do_nothing`: seu `index_where` precisa casar TEXTUALMENTE o
`postgresql_where` do índice parcial `uq_notificacoes_tarefa_aberta` —
se divergir, o Postgres não infere o índice e o INSERT estoura em
runtime. Só um INSERT de verdade contra o banco pega isso.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.services.notificacoes import abrir_tarefa, resolver_tarefas
from tests.api.notificacoes.conftest import ORG, auth

pytestmark = pytest.mark.anyio

TIPO = 'cadastro.incompleto'
CHAVE = 'user:42'


async def _abrir(
    session, *, chave=CHAVE, uae=ORG, titulo='Complete o cadastro'
):
    await abrir_tarefa(
        session,
        uae=uae,
        tipo=TIPO,
        titulo=titulo,
        req_resource='users',
        req_action='update',
        chave_dedupe=chave,
        recurso='users',
    )
    await session.commit()


async def _contar(session, *, chave=CHAVE):
    return await session.scalar(
        select(func.count())
        .select_from(Notificacao)
        .where(
            Notificacao.tipo == TIPO,
            Notificacao.chave_dedupe == chave,
        )
    )


async def test_reabrir_a_mesma_tarefa_e_no_op(session):
    """O INSERT casa o índice parcial e a segunda emissão não duplica."""
    await _abrir(session)
    await _abrir(session)

    assert await _contar(session) == 1


async def test_chave_diferente_abre_outra(session):
    """O dedupe é por (uae, tipo, chave) — outro alvo é outra tarefa."""
    await _abrir(session, chave='user:42')
    await _abrir(session, chave='user:43')

    assert await _contar(session, chave='user:42') == 1
    assert await _contar(session, chave='user:43') == 1


async def test_resolvida_sai_do_indice_e_pode_reabrir(session):
    """Resolvida deixa o índice parcial: a próxima ocorrência abre de novo."""
    await _abrir(session)
    resolvidas = await resolver_tarefas(
        session, uae=ORG, tipo=TIPO, chave_dedupe=CHAVE
    )
    await session.commit()
    assert resolvidas == 1

    await _abrir(session)

    assert await _contar(session) == 2
    abertas = await session.scalar(
        select(func.count())
        .select_from(Notificacao)
        .where(
            Notificacao.chave_dedupe == CHAVE,
            Notificacao.resolved_at.is_(None),
        )
    )
    assert abertas == 1


async def test_resolver_e_idempotente_e_preserva_quem_resolveu(session, users):
    """A segunda resolução não sobrescreve o histórico da primeira."""
    user, other_user = users
    await _abrir(session)

    primeira = await resolver_tarefas(
        session, uae=ORG, tipo=TIPO, chave_dedupe=CHAVE, resolved_by=user.id
    )
    await session.commit()

    segunda = await resolver_tarefas(
        session,
        uae=ORG,
        tipo=TIPO,
        chave_dedupe=CHAVE,
        resolved_by=other_user.id,
    )
    await session.commit()

    assert (primeira, segunda) == (1, 0)

    notif = await session.scalar(
        select(Notificacao).where(Notificacao.chave_dedupe == CHAVE)
    )
    assert notif.resolved_by == user.id


async def test_resolver_nao_alcanca_outra_org(session):
    """A chave é por org: resolver na 1gt não fecha a tarefa da 11gt."""
    await _abrir(session, uae=ORG)

    resolvidas = await resolver_tarefas(
        session, uae='1gt', tipo=TIPO, chave_dedupe=CHAVE
    )
    await session.commit()

    assert resolvidas == 0
    notif = await session.scalar(
        select(Notificacao).where(Notificacao.chave_dedupe == CHAVE)
    )
    assert notif.resolved_at is None


async def test_tarefa_aberta_aparece_no_sino_do_admin(client, session, token):
    """Ponta a ponta: o que o serviço abre é o que o gestor vê."""
    await _abrir(session, titulo='Complete o cadastro de um militar')

    response = await client.get('/notificacoes/', headers=auth(token))

    assert response.status_code == HTTPStatus.OK
    titulos = {n['titulo'] for n in response.json()['data']}
    assert 'Complete o cadastro de um militar' in titulos
