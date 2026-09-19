"""Validacao do payload da missao de GLE.

Nao existe rascunho: missao sem trecho ou sem militar nao apura nada — o
`percentual` sairia vazio e a linha da lista, sem periodo. O periodo de cada
trecho e validado no schema e reforcado por `ck_trecho_gle_periodo`.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio

URL = '/cegep/gle/missoes'

TRECHO = {
    'chegada': '2026-04-26T14:15:00',
    'afastamento': '2026-05-29T02:35:00',
}


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def test_recusa_missao_sem_trecho(client, token, users):
    user, _ = users

    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': 'sem trecho',
            'trechos': [],
            'militares_ids': [user.id],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_recusa_missao_sem_militar(client, token, loc_a):
    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': 'sem militar',
            'trechos': [{'loc_esp_id': loc_a.id, **TRECHO}],
            'militares_ids': [],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_recusa_descricao_vazia(client, token, users, loc_a):
    user, _ = users

    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': '   ',
            'trechos': [{'loc_esp_id': loc_a.id, **TRECHO}],
            'militares_ids': [user.id],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_recusa_afastamento_anterior_a_chegada(
    client, token, users, loc_a
):
    user, _ = users

    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': 'periodo invertido',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-05-29T02:35:00',
                    'afastamento': '2026-04-26T14:15:00',
                }
            ],
            'militares_ids': [user.id],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_recusa_militar_repetido(client, token, users, loc_a):
    user, _ = users

    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': 'militar repetido',
            'trechos': [{'loc_esp_id': loc_a.id, **TRECHO}],
            'militares_ids': [user.id, user.id],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_recusa_localidade_inexistente(client, token, users):
    user, _ = users

    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': 'localidade fantasma',
            'trechos': [{'loc_esp_id': 999999, **TRECHO}],
            'militares_ids': [user.id],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_recusa_militar_inexistente(client, token, loc_a):
    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': 'militar fantasma',
            'trechos': [{'loc_esp_id': loc_a.id, **TRECHO}],
            'militares_ids': [999999],
        },
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_descricao_e_gravada_sem_espaco_sobrando(
    client, token, users, loc_a
):
    user, _ = users

    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'descricao': '  OS 168-BAGL  ',
            'trechos': [{'loc_esp_id': loc_a.id, **TRECHO}],
            'militares_ids': [user.id],
        },
    )

    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['descricao'] == 'OS 168-BAGL'
