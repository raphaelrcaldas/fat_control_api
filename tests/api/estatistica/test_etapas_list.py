"""Filtros de `GET /estatistica/etapas/`: esforco aereo e periodo."""

from datetime import date, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
)
from fcontrol_api.models.shared.aeronaves import Aeronave

pytestmark = pytest.mark.anyio

URL = '/estatistica/etapas/'
DIA = date(2026, 9, 6)
PERIODO = {'data_ini': '2026-09-01', 'data_fim': '2026-09-30'}


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _etapa_ids(resp):
    return {e['id'] for m in resp.json()['data'] for e in m['etapas']}


@pytest.fixture
async def etapas_por_esforco(session):
    """Duas etapas, cada uma com uma OI de um esforco diferente.

    `descricao` e coluna computada (`grupo prog [sub_prog] [aplicacao]`):
    a do esforco sem subprograma ("COMAE TRP") e prefixo textual da do
    que tem ("COMAE TRP LOG"). O filtro antigo por substring devolvia as
    duas etapas ao escolher a primeira.
    """
    session.add(Aeronave(matricula='2853', active=True, sit='DI', obs=None))
    curto = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo='COMAE',
        prog='TRP',
        sub_prog=None,
        aplicacao=None,
    )
    longo = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo='COMAE',
        prog='TRP',
        sub_prog='LOG',
        aplicacao=None,
    )
    tipo = TipoMissao(cod='TRP', desc='Transporte')
    missao = Missao(titulo=None, obs=None, uae='11gt')
    session.add_all([curto, longo, tipo, missao])
    await session.flush()

    def etapa(dep, arr):
        return Etapa(
            missao_id=missao.id,
            obs=None,
            data=DIA,
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
            sagem=True,
            parte1=True,
        )

    etapa_curto = etapa(time(8), time(9))
    etapa_longo = etapa(time(10), time(11))
    session.add_all([etapa_curto, etapa_longo])
    await session.flush()

    session.add_all([
        OIEtapa(
            etapa_id=etapa_curto.id,
            esf_aer_id=curto.id,
            tipo_missao_id=tipo.id,
            reg='d',
            tvoo=60,
        ),
        OIEtapa(
            etapa_id=etapa_longo.id,
            esf_aer_id=longo.id,
            tipo_missao_id=tipo.id,
            reg='d',
            tvoo=60,
        ),
    ])
    await session.commit()
    return {
        'curto': (curto.id, etapa_curto.id),
        'longo': (longo.id, etapa_longo.id),
        'tipo': tipo.id,
    }


async def test_esf_aer_id_casa_por_id_exato(client, token, etapas_por_esforco):
    esf_curto, etapa_curto = etapas_por_esforco['curto']

    resp = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': esf_curto},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert _etapa_ids(resp) == {etapa_curto}


async def test_esf_aer_id_do_esforco_mais_longo(
    client, token, etapas_por_esforco
):
    esf_longo, etapa_longo = etapas_por_esforco['longo']

    resp = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': esf_longo},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert _etapa_ids(resp) == {etapa_longo}


async def test_sem_esf_aer_id_traz_todas(client, token, etapas_por_esforco):
    resp = await client.get(URL, params=PERIODO, headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert _etapa_ids(resp) >= {
        etapas_por_esforco['curto'][1],
        etapas_por_esforco['longo'][1],
    }


@pytest.mark.parametrize('valor', ['0', '-1', '32768', 'abc'])
async def test_esf_aer_id_fora_do_dominio_422(client, token, valor):
    """`gt=0` e teto do smallint (`EsforcoAereo.id`): acima, o asyncpg
    recusaria o parametro com 500."""
    resp = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': valor},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_periodo_invertido_422_com_mensagem(client, token):
    resp = await client.get(
        URL,
        params={'data_ini': '2026-09-30', 'data_fim': '2026-09-01'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp.json()['message'] == (
        'A data inicial não pode ser posterior à data final'
    )


async def test_periodo_de_um_dia_e_valido(client, token, etapas_por_esforco):
    resp = await client.get(
        URL,
        params={'data_ini': DIA.isoformat(), 'data_fim': DIA.isoformat()},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert _etapa_ids(resp) >= {
        etapas_por_esforco['curto'][1],
        etapas_por_esforco['longo'][1],
    }


async def test_esf_aer_id_no_teto_do_smallint_e_valido(client, token):
    resp = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': '32767'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert _etapa_ids(resp) == set()


async def test_esf_aer_id_nao_vaza_etapa_de_outra_org(
    client, session, token, etapas_por_esforco
):
    """Mesmo esforco e mesma data em missao da 1gt: nao aparece na 11gt."""
    esf_curto, etapa_curto = etapas_por_esforco['curto']
    externa = Missao(titulo=None, obs=None, uae='1gt')
    session.add(externa)
    await session.flush()
    etapa_externa = Etapa(
        missao_id=externa.id,
        obs=None,
        data=DIA,
        origem='SBGL',
        destino='SBBR',
        dep=time(14),
        arr=time(15),
        anv='2853',
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
    session.add(etapa_externa)
    await session.flush()
    session.add(
        OIEtapa(
            etapa_id=etapa_externa.id,
            esf_aer_id=esf_curto,
            tipo_missao_id=etapas_por_esforco['tipo'],
            reg='d',
            tvoo=60,
        )
    )
    await session.commit()

    resp = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': esf_curto},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert _etapa_ids(resp) == {etapa_curto}


async def test_esf_aer_id_e_tipo_casam_na_mesma_oi(
    client, session, token, etapas_por_esforco
):
    """Os dois filtros valem para a MESMA OI, nao para OIs diferentes.

    A etapa tem (esforco curto, tipo A) e (esforco longo, tipo B): pedir
    esforco curto + tipo B nao pode trazê-la, embora cada condicao case
    com alguma OI dela.
    """
    esf_curto, _ = etapas_por_esforco['curto']
    esf_longo, _ = etapas_por_esforco['longo']
    tipo_a = etapas_por_esforco['tipo']
    tipo_b = TipoMissao(cod='REVO', desc='Reabastecimento')
    missao = Missao(titulo=None, obs=None, uae='11gt')
    session.add_all([tipo_b, missao])
    await session.flush()
    etapa = Etapa(
        missao_id=missao.id,
        obs=None,
        data=DIA,
        origem='SBGL',
        destino='SBBR',
        dep=time(16),
        arr=time(18),
        anv='2853',
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
    session.add_all([
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_curto,
            tipo_missao_id=tipo_a,
            reg='d',
            tvoo=60,
        ),
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_longo,
            tipo_missao_id=tipo_b.id,
            reg='d',
            tvoo=60,
        ),
    ])
    await session.commit()

    cruzado = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': esf_curto, 'tipo_missao_cod': 'REVO'},
        headers=_auth(token),
    )
    mesma_oi = await client.get(
        URL,
        params={**PERIODO, 'esf_aer_id': esf_longo, 'tipo_missao_cod': 'REVO'},
        headers=_auth(token),
    )

    assert cruzado.status_code == HTTPStatus.OK
    assert etapa.id not in _etapa_ids(cruzado)
    assert mesma_oi.status_code == HTTPStatus.OK
    assert _etapa_ids(mesma_oi) == {etapa.id}
