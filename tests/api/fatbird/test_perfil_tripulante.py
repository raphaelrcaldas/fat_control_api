"""Perfil e vínculo do tripulante (trip.ts, user.ts).

O portal abre lendo quem é o militar logado: o vínculo de tripulante
(`ops/trips/me`), o perfil (`users/me`) e a ficha completa
(`users/{id}`), que ele também edita. Tudo isso tem de funcionar **sem
role** — e nada disso pode virar porta para a ficha de outro militar.
"""

from http import HTTPStatus

import pytest

from tests.api.fatbird.conftest import auth

pytestmark = pytest.mark.anyio


async def test_trip_me_retorna_o_proprio_vinculo(
    client, trip_user, trip_token
):
    """`ops/trips/me` devolve o tripulante do próprio token."""
    user, trip = trip_user

    resp = await client.get('/ops/trips/me', headers=auth(trip_token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['id'] == trip.id
    assert data['user']['id'] == user.id


async def test_users_me_retorna_o_proprio_perfil(
    client, trip_user, trip_token
):
    """`users/me` devolve o perfil do próprio militar."""
    user, _ = trip_user

    resp = await client.get('/users/me', headers=auth(trip_token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['id'] == user.id
    assert data['nome_guerra'] == user.nome_guerra


async def test_le_a_propria_ficha(client, trip_user, trip_token):
    """`users/{id}` do próprio id funciona sem 'user.view' (é o dono)."""
    user, _ = trip_user

    resp = await client.get(f'/users/{user.id}', headers=auth(trip_token))

    assert resp.status_code == HTTPStatus.OK
    # UserFull herda do payload de criação e não expõe `id` — a identidade
    # vem pelo saram (único) e pela unidade.
    data = resp.json()['data']
    assert data['saram'] == user.saram
    assert data['unidade'] == user.unidade


async def test_edita_a_propria_ficha(client, trip_user, trip_token):
    """O militar atualiza o próprio cadastro pelo portal (sem role)."""
    user, _ = trip_user

    resp = await client.put(
        f'/users/{user.id}',
        json={'telefone': '21999998888'},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['telefone'] == '21999998888'


async def test_nao_edita_a_ficha_de_outro(client, trip_token, outro_trip):
    """Sem 'user.update', não altera o cadastro de outro militar."""
    outro, _ = outro_trip

    resp = await client.put(
        f'/users/{outro.id}',
        json={'telefone': '21911112222'},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_troca_a_propria_senha(client, trip_token):
    """`users/change-pwd` age sobre o usuário do token (sempre o dono)."""
    resp = await client.post(
        '/users/change-pwd',
        json={'new_pwd': 'NovaSenha1!'},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
