"""Sino do FatBird pelo POV do tripulante (sem role nenhuma).

O router de notificações não pode ter `permission_checker`: o tripulante
entra sem `user_roles`, e um gate ali devolveria 403 no sino — que os
fetchers do portal engolem como "sem novidade", virando regressão
silenciosa.

Estes testes usam o token forjado do `conftest` do FatBird (sem role),
não as factories do conftest de cima, que injetam admin.
"""

from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.fatbird.conftest import ORG, auth

pytestmark = pytest.mark.anyio


@pytest.fixture
def semear(session):
    """Insere uma notificação direta para um usuário qualquer."""

    async def _semear(
        user,
        *,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        titulo='Você recebeu 1 quadrinho(s)',
        uae=ORG,
    ):
        notif = Notificacao(
            uae=uae,
            escopo=NotifEscopo.DIRETA.value,
            audiencia=audiencia,
            tipo=NotifTipo.QUADRO_RECEBIDO.value,
            titulo=titulo,
            recurso='ops.quadro',
            user_id=user.id,
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif

    return _semear


@pytest.fixture
def semear_tarefa(session):
    """Insere uma tarefa de gestão na org do tripulante."""

    async def _semear():
        notif = Notificacao(
            uae=ORG,
            escopo=NotifEscopo.TAREFA.value,
            audiencia=NotifAudiencia.GESTOR.value,
            tipo='cadastro.incompleto',
            titulo='Complete o cadastro',
            recurso='users',
            req_resource='users',
            req_action='update',
            chave_dedupe='u:99',
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif

    return _semear


async def test_sino_abre_sem_role(client, trip_user, trip_token, semear):
    """Sem `user_roles` a lista responde 200 (nada de 403 no sino)."""
    user, _ = trip_user
    minha = await semear(user)

    response = await client.get('/notificacoes/', headers=auth(trip_token))

    assert response.status_code == HTTPStatus.OK
    assert {n['id'] for n in response.json()['data']} == {minha.id}


async def test_contador_abre_sem_role(client, trip_user, trip_token, semear):
    user, _ = trip_user
    await semear(user)

    response = await client.get(
        '/notificacoes/contador', headers=auth(trip_token)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['nao_lidas'] == 1


async def test_tripulante_nao_ve_tarefa(
    client, trip_user, trip_token, semear, semear_tarefa
):
    """Tarefa é endereçada por permissão — o tripulante não tem nenhuma."""
    user, _ = trip_user
    minha = await semear(user)
    tarefa = await semear_tarefa()

    lista = await client.get('/notificacoes/', headers=auth(trip_token))
    contador = await client.get(
        '/notificacoes/contador', headers=auth(trip_token)
    )

    ids = {n['id'] for n in lista.json()['data']}
    assert ids == {minha.id}
    assert tarefa.id not in ids
    assert contador.json()['data']['tarefas'] == 0


async def test_tripulante_nao_ve_a_de_outro(
    client, trip_user, trip_token, outro_trip, semear
):
    """Escopo self-service: a caixa é do dono, não da unidade."""
    user, _ = trip_user
    outro_user, _ = outro_trip
    minha = await semear(user)
    dele = await semear(outro_user)

    lista = await client.get('/notificacoes/', headers=auth(trip_token))

    ids = {n['id'] for n in lista.json()['data']}
    assert minha.id in ids
    assert dele.id not in ids


async def test_tripulante_marca_lida(client, trip_user, trip_token, semear):
    user, _ = trip_user
    minha = await semear(user)

    response = await client.patch(
        f'/notificacoes/{minha.id}/lida', headers=auth(trip_token)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['read_at'] is not None

    contador = await client.get(
        '/notificacoes/contador', headers=auth(trip_token)
    )
    assert contador.json()['data']['total'] == 0


async def test_tripulante_marca_todas_lidas(
    client, trip_user, trip_token, semear
):
    user, _ = trip_user
    await semear(user, titulo='A')
    await semear(user, titulo='B')

    response = await client.post(
        '/notificacoes/marcar-todas-lidas', headers=auth(trip_token)
    )

    assert response.status_code == HTTPStatus.OK
    contador = await client.get(
        '/notificacoes/contador', headers=auth(trip_token)
    )
    assert contador.json()['data']['nao_lidas'] == 0


async def test_quadrinho_lancado_no_client_chega_no_sino_do_portal(
    client, session, trip_user, trip_token, token
):
    """Ponta a ponta: gestor lança pelo client, tripulante vê no FatBird.

    É o fluxo que a v1 existe para provar — inclusive que a audiência
    `tripulante` da emissão casa com a do token do portal.
    """
    _, trip = trip_user

    lancamento = await client.post(
        '/ops/quads/',
        json=[
            {
                'value': date.today().isoformat(),
                'type_id': 1,
                'description': 'x',
                'trip_id': trip.id,
            }
        ],
        headers={'Authorization': f'Bearer {token}'},
    )
    assert lancamento.status_code == HTTPStatus.CREATED

    contador = await client.get(
        '/notificacoes/contador', headers=auth(trip_token)
    )
    assert contador.json()['data']['nao_lidas'] == 1

    lista = await client.get('/notificacoes/', headers=auth(trip_token))
    item = lista.json()['data'][0]
    assert item['tipo'] == NotifTipo.QUADRO_RECEBIDO.value
    assert item['payload']['quantidade'] == 1
    assert item['payload']['func'] == trip.func
    assert item['payload']['tipo'] == {
        'id': 1,
        'nome': 'preto',
        'grupo': 'sobreaviso',
    }
