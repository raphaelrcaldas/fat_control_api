"""Documentos do militar no FatBird (cartoes.ts).

A tela "Meus cartões" busca cartão de saúde, CRM e passaporte pelo
`user_id`. Os três recursos são administrativos ('cartoes-saude', 'crm',
'passaportes') e o tripulante não tem nenhum — então os três dependem do
bypass de dono. Quando não há cadastro, o portal espera "sem documento"
(200/None ou 404), nunca 403: o fetcher só engole 404, e um 403 viraria
"tudo em ordem" numa tela de vencimentos.
"""

from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.inteligencia.passaportes import Passaporte
from fcontrol_api.models.seg_voo.crm import CrmCertificado
from tests.api.fatbird.conftest import auth

pytestmark = pytest.mark.anyio


# ── Cartão de saúde ────────────────────────────────────────────────


async def test_le_o_proprio_cartao_saude(
    client, session, trip_user, trip_token
):
    """O militar vê o próprio cartão sem 'cartoes-saude.view'."""
    user, _ = trip_user
    cartao = CartaoSaude(
        user_id=user.id,
        cemal=date(2027, 1, 1),
        tovn=None,
        imae=None,
        prontuario='123',
    )
    session.add(cartao)
    await session.commit()

    resp = await client.get(
        f'/aeromedica/cartoes-saude/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == cartao.id


async def test_cartao_saude_sem_cadastro_nao_da_403(
    client, trip_user, trip_token
):
    """Sem cartão cadastrado o portal recebe 'sem documento', não 403."""
    user, _ = trip_user

    resp = await client.get(
        f'/aeromedica/cartoes-saude/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None


# ── CRM ────────────────────────────────────────────────────────────


async def test_le_o_proprio_crm(client, session, trip_user, trip_token):
    """O militar vê o próprio CRM sem 'crm.view'."""
    user, _ = trip_user
    crm = CrmCertificado(
        user_id=user.id,
        data_realizacao=date(2025, 1, 1),
        data_validade=date(2027, 1, 1),
    )
    session.add(crm)
    await session.commit()

    resp = await client.get(
        f'/seg-voo/crm/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == crm.id


async def test_crm_sem_cadastro_nao_da_403(client, trip_user, trip_token):
    """Sem CRM cadastrado o portal recebe 'sem documento', não 403."""
    user, _ = trip_user

    resp = await client.get(
        f'/seg-voo/crm/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None


# ── Passaporte ─────────────────────────────────────────────────────


async def test_le_o_proprio_passaporte(client, session, trip_user, trip_token):
    """O militar vê o próprio passaporte sem 'passaportes.view'."""
    user, _ = trip_user
    pp = Passaporte(
        user_id=user.id,
        passaporte='AB123456',
        data_expedicao_passaporte=None,
        validade_passaporte=date(2030, 1, 1),
        visa=None,
        data_expedicao_visa=None,
        validade_visa=None,
        passaporte_file_path=None,
        visa_file_path=None,
    )
    session.add(pp)
    await session.commit()

    resp = await client.get(
        f'/inteligencia/passaportes/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == pp.id


async def test_passaporte_sem_cadastro_nao_da_403(
    client, trip_user, trip_token
):
    """Sem passaporte cadastrado o portal recebe 'sem documento'."""
    user, _ = trip_user

    resp = await client.get(
        f'/inteligencia/passaportes/user/{user.id}', headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] is None
