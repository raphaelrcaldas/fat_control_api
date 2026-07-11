"""Aba financeira do FatBird (cegep.ts).

O militar consulta os próprios comissionamentos, os dados bancários e os
pagamentos lavrados. São dados de PII/financeiro — os recursos
(`comiss`, `dados_bancarios`, `missoes_cegep`) são administrativos e o
tripulante NÃO os tem. Logo, tudo aqui depende do bypass de dono; e a
contrapartida é que o dado de outro militar tem de fechar em 403.
"""

from http import HTTPStatus

import pytest

from tests.api.fatbird.conftest import auth
from tests.factories import ComissFactory, DadosBancariosFactory

pytestmark = pytest.mark.anyio


# ── Comissionamentos ───────────────────────────────────────────────


async def test_lista_os_proprios_comiss(
    client, session, trip_user, trip_token
):
    """A lista filtrada pelo próprio user_id sai sem 'comiss.view'."""
    user, _ = trip_user
    comiss = ComissFactory(user_id=user.id, uae='11gt')
    session.add(comiss)
    await session.commit()

    resp = await client.get(
        '/cegep/comiss/',
        params={'user_id': user.id},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK
    ids = {c['id'] for c in resp.json()['data']}
    assert comiss.id in ids


async def test_nao_lista_comiss_de_outro(
    client, session, trip_token, outro_trip
):
    """Filtrar pelo user_id de outro militar é negado (não é o dono)."""
    outro, _ = outro_trip
    session.add(ComissFactory(user_id=outro.id, uae='11gt'))
    await session.commit()

    resp = await client.get(
        '/cegep/comiss/',
        params={'user_id': outro.id},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_abre_o_proprio_comiss(client, session, trip_user, trip_token):
    """O detalhe do próprio comissionamento abre sem a permissão."""
    user, _ = trip_user
    comiss = ComissFactory(user_id=user.id, uae='11gt')
    session.add(comiss)
    await session.commit()

    resp = await client.get(
        f'/cegep/comiss/{comiss.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == comiss.id


async def test_nao_abre_o_comiss_de_outro(
    client, session, trip_token, outro_trip
):
    """O detalhe do comissionamento de outro militar fecha em 403."""
    outro, _ = outro_trip
    comiss = ComissFactory(user_id=outro.id, uae='11gt')
    session.add(comiss)
    await session.commit()

    resp = await client.get(
        f'/cegep/comiss/{comiss.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN


# ── Dados bancários ────────────────────────────────────────────────


async def test_le_os_proprios_dados_bancarios(
    client, session, trip_user, trip_token
):
    """O militar vê a própria conta sem 'dados_bancarios.view'.

    Regressão: este endpoint estava gated puro e devolvia 403 ao dono.
    """
    user, _ = trip_user
    dados = DadosBancariosFactory(user_id=user.id)
    session.add(dados)
    await session.commit()

    resp = await client.get(
        f'/cegep/dados-bancarios/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['banco'] == dados.banco


async def test_nao_le_dados_bancarios_de_outro(
    client, session, trip_token, outro_trip
):
    """A conta bancária de outro militar fecha em 403."""
    outro, _ = outro_trip
    session.add(DadosBancariosFactory(user_id=outro.id))
    await session.commit()

    resp = await client.get(
        f'/cegep/dados-bancarios/user/{outro.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN


# ── Pagamentos (financeiro) ────────────────────────────────────────


async def test_consulta_os_proprios_pagamentos(client, trip_user, trip_token):
    """Os pagamentos filtrados pelo próprio user_id saem sem a permissão."""
    user, _ = trip_user

    resp = await client.get(
        '/cegep/financeiro/pgts',
        params={'user_id': user.id, 'sit': ['d', 'g'], 'page': 1, 'limit': 20},
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.OK


async def test_nao_consulta_pagamentos_de_outro(
    client, trip_token, outro_trip
):
    """Sem 'missoes_cegep.view', não consulta o pagamento de outro."""
    outro, _ = outro_trip

    resp = await client.get(
        '/cegep/financeiro/pgts',
        params={
            'user_id': outro.id,
            'sit': ['d', 'g'],
            'page': 1,
            'limit': 20,
        },
        headers=auth(trip_token),
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN
