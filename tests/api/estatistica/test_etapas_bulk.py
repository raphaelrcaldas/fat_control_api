"""Atualizacao atomica das flags SAGEM e Parte 1."""

from datetime import date, time
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.estatistica.etapa import Etapa, Missao
from fcontrol_api.models.shared.aeronaves import Aeronave

pytestmark = pytest.mark.anyio

URL = '/estatistica/etapas/bulk'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def etapas_bulk(session):
    session.add(Aeronave(matricula='2853', active=True, sit='DI', obs=None))
    missao_ativa = Missao(titulo=None, obs=None, uae='11gt')
    missao_externa = Missao(titulo=None, obs=None, uae='1gt')
    session.add_all([missao_ativa, missao_externa])
    await session.flush()

    def etapa(missao_id, dep, arr):
        return Etapa(
            missao_id=missao_id,
            obs=None,
            data=date(2026, 9, 6),
            origem='SBGL',
            destino='SBBR',
            dep=dep,
            arr=arr,
            anv='2853',
            pousos=1,
            tow=None,
            pax=None,
            carga=None,
            comb=None,
            lub=None,
            nivel=None,
            sagem=False,
            parte1=False,
        )

    primeira = etapa(missao_ativa.id, time(8), time(9))
    segunda = etapa(missao_ativa.id, time(10), time(11))
    externa = etapa(missao_externa.id, time(12), time(13))
    session.add_all([primeira, segunda, externa])
    await session.commit()
    return primeira, segunda, externa


async def test_bulk_atualiza_todas_em_um_commit(
    client, session, token, etapas_bulk
):
    primeira, segunda, _ = etapas_bulk
    ids = [primeira.id, segunda.id]

    response = await client.patch(
        URL,
        json={
            'ids': ids,
            'data': {'sagem': True},
        },
        headers=_auth(token),
    )

    assert response.status_code == HTTPStatus.OK
    session.expire_all()
    atualizadas = list(
        (
            await session.scalars(
                select(Etapa).where(Etapa.id.in_(ids)).order_by(Etapa.id)
            )
        ).all()
    )
    assert [etapa.sagem for etapa in atualizadas] == [True, True]
    assert [etapa.parte1 for etapa in atualizadas] == [False, False]


async def test_bulk_rejeita_lote_cross_org_sem_atualizar_parcialmente(
    client, session, token, etapas_bulk
):
    primeira, _, externa = etapas_bulk

    response = await client.patch(
        URL,
        json={
            'ids': [primeira.id, externa.id],
            'data': {'parte1': True},
        },
        headers=_auth(token),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    await session.refresh(primeira)
    await session.refresh(externa)
    assert primeira.parte1 is False
    assert externa.parte1 is False


async def test_bulk_exige_algum_campo(client, token, etapas_bulk):
    primeira, _, _ = etapas_bulk

    response = await client.patch(
        URL,
        json={'ids': [primeira.id], 'data': {}},
        headers=_auth(token),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
