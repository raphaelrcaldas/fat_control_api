"""Poda das notificações encerradas.

A regra que importa aqui é a do docstring da task: sai o que teve
DESFECHO (lida/resolvida) há mais de N dias — pendente antiga fica, por
mais velha que seja. Notificação sem desfecho ainda é trabalho a fazer.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from fcontrol_api.cleanup.tasks.old_notificacoes import run
from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.shared.notificacao import Notificacao

pytestmark = pytest.mark.anyio

ORG = '11gt'


async def _mk_direta(session, user, *, read_at=None):
    notif = Notificacao(
        uae=ORG,
        escopo=NotifEscopo.DIRETA.value,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        tipo=NotifTipo.QUADRO_RECEBIDO.value,
        titulo='Você recebeu 1 quadrinho(s)',
        recurso='ops.quadro',
        user_id=user.id,
        read_at=read_at,
    )
    session.add(notif)
    await session.commit()
    await session.refresh(notif)
    return notif


async def test_apaga_direta_lida_antiga(session, users):
    user, _ = users
    antiga = datetime.now(timezone.utc) - timedelta(days=120)
    notif = await _mk_direta(session, user, read_at=antiga)

    result = await run(session)

    assert result.status == 'success'
    assert result.rows_affected == 1
    assert result.task_name == 'cleanup_old_notificacoes'

    restante = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif.id)
    )
    assert restante is None


async def test_mantem_direta_lida_recente(session, users):
    user, _ = users
    recente = datetime.now(timezone.utc) - timedelta(days=10)
    notif = await _mk_direta(session, user, read_at=recente)

    result = await run(session)

    assert result.status == 'skipped'

    restante = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif.id)
    )
    assert restante is not None


async def test_mantem_pendente_por_mais_antiga_que_seja(session, users):
    """A regra central: sem desfecho, não sai — nem com anos de idade."""
    user, _ = users
    notif = await _mk_direta(session, user, read_at=None)

    result = await run(session)

    assert result.status == 'skipped'
    assert result.rows_affected == 0

    restante = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif.id)
    )
    assert restante is not None


async def test_apaga_tarefa_resolvida_antiga(session, users):
    """Tarefa usa a coluna do PRÓPRIO desfecho (`resolved_at`)."""
    user, _ = users
    antiga = datetime.now(timezone.utc) - timedelta(days=200)
    tarefa = Notificacao(
        uae=ORG,
        escopo=NotifEscopo.TAREFA.value,
        audiencia=NotifAudiencia.GESTOR.value,
        tipo='cadastro.incompleto',
        titulo='Complete o cadastro de um militar',
        recurso='users',
        req_resource='users',
        req_action='update',
        chave_dedupe=f'user:{user.id}',
        resolved_by=user.id,
        resolved_at=antiga,
    )
    session.add(tarefa)
    await session.commit()
    await session.refresh(tarefa)

    result = await run(session)

    assert result.status == 'success'
    assert result.rows_affected == 1

    restante = await session.scalar(
        select(Notificacao).where(Notificacao.id == tarefa.id)
    )
    assert restante is None


async def test_sem_candidatos(session, users):
    result = await run(session)

    assert result.task_name == 'cleanup_old_notificacoes'
    assert result.status == 'skipped'
    assert result.rows_affected == 0
    assert result.details['reason'] == 'Nenhuma notificação encerrada antiga'


async def test_erro_de_banco_vira_status_error(session, users):
    with patch.object(
        session,
        'execute',
        new_callable=AsyncMock,
        side_effect=RuntimeError('conexao perdida'),
    ):
        result = await run(session)

    assert result.task_name == 'cleanup_old_notificacoes'
    assert result.status == 'error'
    assert result.rows_affected == 0
    assert 'conexao perdida' in result.errors[0]
