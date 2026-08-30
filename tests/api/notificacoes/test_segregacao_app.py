"""Segregação por app (`audiencia` × `app_client` do token).

A MESMA pessoa é gestora no client e tripulante no FatBird. O que ela vê
no sino depende do app pelo qual entrou, e isso é imposto no backend: o
front não escolhe. Sem essa amarra, o item de quadrinho apareceria no
client com um deep-link para uma rota que só existe no FatBird.

Os testes usam um único usuário com DOIS tokens (client e FatBird) — é o
cenário que a decisão precisa sustentar.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.enums.notificacao import NotifAudiencia
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import auth, fatbird_token

pytestmark = pytest.mark.anyio


@pytest.fixture
async def notif_tripulante(users, make_direta):
    """Notificação de quadrinho (audiência tripulante) do primeiro user."""
    user, _ = users
    return await make_direta(
        user,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        titulo='Você recebeu 1 quadrinho(s)',
    )


@pytest.fixture
async def notif_gestor(users, make_direta):
    """Notificação de gestão (audiência gestor) do mesmo user."""
    user, _ = users
    return await make_direta(
        user,
        audiencia=NotifAudiencia.GESTOR.value,
        titulo='Missão atualizada',
    )


# ── Token do client não enxerga o que é do tripulante ───────────────


async def test_client_nao_lista_notificacao_de_tripulante(
    client, token, notif_tripulante
):
    response = await client.get('/notificacoes/', headers=auth(token))

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body['total'] == 0
    assert notif_tripulante.id not in {n['id'] for n in body['data']}


async def test_client_nao_conta_notificacao_de_tripulante(
    client, token, notif_tripulante
):
    response = await client.get('/notificacoes/contador', headers=auth(token))

    assert response.json()['data'] == {
        'nao_lidas': 0,
        'tarefas': 0,
        'total': 0,
    }


async def test_client_nao_marca_lida_de_tripulante(
    client, session, token, notif_tripulante
):
    """404 (não 403): para o token do client, a linha nem existe."""
    response = await client.patch(
        f'/notificacoes/{notif_tripulante.id}/lida', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND

    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif_tripulante.id)
    )
    assert db_notif.read_at is None


async def test_marcar_todas_lidas_do_client_nao_toca_no_tripulante(
    client, session, token, notif_tripulante
):
    """O UPDATE em lote também filtra por audiência."""
    await client.post('/notificacoes/marcar-todas-lidas', headers=auth(token))

    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif_tripulante.id)
    )
    assert db_notif.read_at is None


# ── ...e o inverso: token do FatBird não enxerga o de gestão ────────


async def test_fatbird_nao_lista_notificacao_de_gestor(
    client, users, trips, notif_gestor
):
    user, _ = users
    response = await client.get(
        '/notificacoes/', headers=auth(fatbird_token(user))
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['total'] == 0


async def test_fatbird_nao_marca_lida_de_gestor(
    client, session, users, trips, notif_gestor
):
    user, _ = users
    response = await client.patch(
        f'/notificacoes/{notif_gestor.id}/lida',
        headers=auth(fatbird_token(user)),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND

    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif_gestor.id)
    )
    assert db_notif.read_at is None


async def test_mesma_pessoa_ve_caixas_diferentes_por_app(
    client, users, trips, notif_gestor, notif_tripulante
):
    """O caso que motiva a decisão: um usuário, dois sinos disjuntos."""
    user, _ = users

    no_fatbird = await client.get(
        '/notificacoes/', headers=auth(fatbird_token(user))
    )

    assert {n['id'] for n in no_fatbird.json()['data']} == {
        notif_tripulante.id
    }


async def test_fatbird_marca_lida_a_propria(
    client, users, trips, notif_tripulante
):
    """O tripulante resolve a caixa dele normalmente."""
    user, _ = users
    token = fatbird_token(user)

    response = await client.patch(
        f'/notificacoes/{notif_tripulante.id}/lida', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['read_at'] is not None

    contador = await client.get('/notificacoes/contador', headers=auth(token))
    assert contador.json()['data']['total'] == 0


async def test_client_nao_apaga_notificacao_de_tripulante(
    client, session, users, token, notif_tripulante
):
    """Apagar respeita a mesma amarra de audiência das outras mutações."""
    response = await client.delete(
        f'/notificacoes/{notif_tripulante.id}', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == notif_tripulante.id)
    )
    assert db_notif is not None


async def test_fatbird_apaga_a_propria(client, users, trips, notif_tripulante):
    """No portal o tripulante apaga a dele normalmente."""
    user, _ = users
    token = fatbird_token(user)

    response = await client.delete(
        f'/notificacoes/{notif_tripulante.id}', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.OK

    lista = await client.get('/notificacoes/', headers=auth(token))
    assert lista.json()['total'] == 0
