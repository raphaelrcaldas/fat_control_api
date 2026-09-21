"""Pesquisa preserva evidências, filtros e isolamento da organização."""

from datetime import date, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.etapa import (
    EsforcoAereo,
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
)
from fcontrol_api.models.shared.aeronaves import Aeronave
from tests.factories import LocEspIcaoFactory

pytestmark = pytest.mark.anyio
URL = '/cegep/gle/pesquisa'


@pytest.fixture
async def passagens(session, loc_a_com_icao, loc_b):
    session.add(LocEspIcaoFactory(loc_esp_id=loc_b.id, icao='SBPJ'))
    esf = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo='COMPREP',
        prog='PRPO',
        sub_prog=None,
        aplicacao=None,
    )
    tipo = TipoMissao(cod='ADT', desc='Adestramento')
    session.add_all([esf, tipo])
    await session.flush()
    anv = '2850'
    session.add(Aeronave(matricula=anv, active=True, sit='DI', obs=None))
    await session.flush()
    validas = []
    for org, simulador, com_oi in [
        ('11gt', False, True),
        ('1gt', False, True),
        ('11gt', True, True),
        ('11gt', False, False),
    ]:
        missao = Missao(
            titulo='OM GLE', obs=None, uae=org, is_simulador=simulador
        )
        session.add(missao)
        await session.flush()
        etapa = Etapa(
            missao_id=missao.id,
            obs=None,
            data=date(2026, 4, 26),
            origem='SBBV',
            destino='SBPJ',
            dep=time(10),
            arr=time(11),
            anv=anv,
            pousos=1,
            tow=None,
            pax=None,
            carga=None,
            comb=None,
            lub=None,
            nivel=None,
            sagem=True,
            parte1=True,
        )
        session.add(etapa)
        await session.flush()
        if com_oi:
            # Duas OIs não podem duplicar a evidência da mesma etapa.
            session.add_all([
                OIEtapa(
                    etapa_id=etapa.id,
                    esf_aer_id=esf.id,
                    tvoo=30,
                    reg=reg,
                    tipo_missao_id=tipo.id,
                )
                for reg in ('d', 'n')
            ])
        if org == '11gt' and not simulador and com_oi:
            validas.append(missao.id)
    await session.commit()
    return validas


@pytest.mark.parametrize(
    ('params', 'icaos', 'grupos'),
    [
        ({}, ['SBBV', 'SBPJ'], [1, 2]),
        ({'grupo': 1}, ['SBBV'], [1]),
        ({'grupo': 2}, ['SBPJ'], [2]),
    ],
)
async def test_pesquisa_filtra_pontas_e_escopo(
    client, token, passagens, params, icaos, grupos
):
    response = await client.get(
        URL, headers={'Authorization': f'Bearer {token}'}, params=params
    )
    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['total_missoes'] == 1
    assert [m['missao_id'] for m in data['missoes']] == passagens
    missao = data['missoes'][0]
    assert missao['total_etapas'] == 1
    assert missao['etapas'][0]['icaos_loc_esp'] == icaos
    assert sorted(loc['grupo'] for loc in missao['localidades']) == grupos


@pytest.mark.parametrize(
    'params',
    [
        {'data_ini': '2026-04-27'},
        {'data_fim': '2026-04-25'},
        {'loc_esp_id': 999999},
    ],
)
async def test_pesquisa_sem_correspondencia(client, token, passagens, params):
    response = await client.get(
        URL, headers={'Authorization': f'Bearer {token}'}, params=params
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['data'] == {'total_missoes': 0, 'missoes': []}


async def test_filtro_localidade(client, token, passagens, loc_b):
    response = await client.get(
        URL,
        headers={'Authorization': f'Bearer {token}'},
        params={'loc_esp_id': loc_b.id},
    )
    assert response.status_code == HTTPStatus.OK
    missao = response.json()['data']['missoes'][0]
    assert [loc['loc_esp_id'] for loc in missao['localidades']] == [loc_b.id]
    assert missao['etapas'][0]['icaos_loc_esp'] == ['SBPJ']


@pytest.mark.parametrize('url', ['/cegep/gle', URL])
async def test_sem_permissao(client, token_sem_perm, url):
    response = await client.get(
        url, headers={'Authorization': f'Bearer {token_sem_perm}'}
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_pesquisa_exige_org_ativa(client, token_sistema):
    response = await client.get(
        URL, headers={'Authorization': f'Bearer {token_sistema}'}
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
