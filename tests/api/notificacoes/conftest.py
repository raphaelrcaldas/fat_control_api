"""Fixtures do sino de notificações.

Duas peças que os testes daqui não conseguem obter do conftest de cima:

1. **Semeadura direta no banco** — a v1 só emite um evento (quadrinho, de
   audiência `tripulante`). Tarefas e notificações de `gestor` não têm
   emissor, então a única forma de exercitar leitura/resolução é inserir
   a linha pelo model.
2. **Token do FatBird forjado na mão** — `make_org_token`/`make_token`
   injetam uma role admin quando o usuário não tem nenhuma, e o que se
   quer provar aqui é a segregação por `app_client`, não o bypass.
"""

import pytest

from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.security import create_access_token
from tests.factories import TripFactory

ORG = '11gt'


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def fatbird_token(user, active_org=ORG):
    """Token como o portal do tripulante emite: `app_client='fatbird'`.

    Forjado direto (sem passar pelas factories de token) justamente para
    NÃO ganhar role: o tripulante do FatBird não tem nenhuma, e uma role
    admin injetada mascararia a segregação que estes testes cobram.

    O user precisa ser TRIPULANTE ATIVO (fixture `trips`) — o
    `validate_user_client_access` recheca isso a cada request do
    app_client 'fatbird' e devolve 403 para quem não é.
    """
    return create_access_token(
        data={
            'sub': f'tripulante {user.id}',
            'user_id': user.id,
            'app_client': 'fatbird',
            'active_org': active_org,
        }
    )


@pytest.fixture
async def trips(session, users):
    """Um tripulante para cada usuário da fixture `users`, na '11gt'.

    O primeiro é o do AUTOR dos lançamentos (a fixture `token` é dele) —
    é com ele que se prova que ninguém se auto-notifica.
    """
    user, other_user = users

    trip = TripFactory(user_id=user.id, uae=ORG)
    other_trip = TripFactory(user_id=other_user.id, uae=ORG)

    session.add_all([trip, other_trip])
    await session.commit()
    await session.refresh(trip)
    await session.refresh(other_trip)

    return trip, other_trip


@pytest.fixture
def make_direta(session):
    """Semeia uma notificação DIRETA endereçada a um usuário."""

    async def _make(
        user,
        *,
        audiencia=NotifAudiencia.GESTOR.value,
        uae=ORG,
        tipo=NotifTipo.QUADRO_RECEBIDO.value,
        titulo='Notificação direta',
        recurso='ops.quadro',
        recurso_id=None,
        read_at=None,
        created_by=None,
        payload=None,
    ):
        notif = Notificacao(
            uae=uae,
            escopo=NotifEscopo.DIRETA.value,
            audiencia=audiencia,
            tipo=tipo,
            titulo=titulo,
            recurso=recurso,
            recurso_id=recurso_id,
            user_id=user.id,
            read_at=read_at,
            created_by=created_by,
            payload=payload or {},
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif

    return _make


@pytest.fixture
def make_tarefa(session):
    """Semeia uma TAREFA (endereçada por permissão, audiência gestor).

    Não há emissor na v1 — a tarefa nasce aqui para provar visibilidade,
    isolamento por org e o contrato do `/resolver`.
    """

    async def _make(
        *,
        uae=ORG,
        tipo='cadastro.incompleto',
        titulo='Complete o cadastro de um militar',
        recurso='users',
        req_resource='users',
        req_action='update',
        chave_dedupe='user:1',
        recurso_id=None,
    ):
        notif = Notificacao(
            uae=uae,
            escopo=NotifEscopo.TAREFA.value,
            audiencia=NotifAudiencia.GESTOR.value,
            tipo=tipo,
            titulo=titulo,
            recurso=recurso,
            recurso_id=recurso_id,
            req_resource=req_resource,
            req_action=req_action,
            chave_dedupe=chave_dedupe,
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif

    return _make
