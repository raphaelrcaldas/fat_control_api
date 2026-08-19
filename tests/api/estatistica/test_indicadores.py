"""Painel anual de indicadores — GET /estatistica/indicadores.

O teste que justifica este arquivo é o de **fan-out**. `Etapa` é 1:N com
`OIEtapa`, `PqdEtapa`, `REVOEtapa` e `HeavyCDS` ao mesmo tempo; um JOIN
das quatro multiplicaria `carga`, `pax` e `comb` pelo produto cartesiano
das filhas. O endpoint evita isso com uma CTE de escopo (uma linha por
etapa) e agregações independentes — se alguém consolidar tudo num JOIN,
a tela continua carregando e passa a mentir. É falha silenciosa, e é
`test_fan_out_nao_multiplica_metricas_da_etapa` que a pega.
"""

from datetime import date, time
from decimal import Decimal
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    HeavyCDS,
    Missao,
    OIEtapa,
    PqdEtapa,
    REVOEtapa,
    TipoMissao,
)
from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.shared.aeronaves import Aeronave

pytestmark = pytest.mark.anyio

URL = '/estatistica/indicadores/'
ANO = 2025


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _mk_etapa(session, missao_id, *, anv, **campos):
    """Etapa de 150 min (10:00→12:30); `tvoo` é coluna computada."""
    padrao = {
        'obs': None,
        'data': date(ANO, 3, 10),
        'origem': 'SBGL',
        'destino': 'SBBR',
        'dep': time(10, 0),
        'arr': time(12, 30),
        'pousos': 1,
        'tow': None,
        'pax': None,
        'carga': None,
        'comb': None,
        'lub': None,
        'nivel': None,
        'sagem': True,
        'parte1': True,
    }
    padrao.update(campos)
    etapa = Etapa(missao_id=missao_id, anv=anv, **padrao)
    session.add(etapa)
    await session.flush()
    return etapa


@pytest.fixture
async def refs(session):
    """EsforcoAereo + TipoMissao para compor os OIs."""
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
    await session.commit()
    return esf.id, tipo.id


@pytest.fixture
async def etapa_com_filhas(session, refs):
    """Uma ÚNICA etapa da '11gt' com múltiplas filhas de cada tipo.

    2 OIs + 2 PQD + 1 REVO + 3 lançamentos. Um JOIN ingênuo das quatro
    tabelas produziria 2*2*1*3 = 12 linhas por etapa, inflando carga,
    pax e comb em 12x.
    """
    esf_id, tipo_id = refs

    session.add(Aeronave(matricula='2850', active=True, sit='DI', obs=None))
    missao = Missao(titulo=None, obs=None, uae='11gt')
    session.add(missao)
    await session.flush()

    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        pax=10,
        carga=1000,
        comb=500,
        lub=Decimal('2.5'),
    )

    # 2 OIs: o rateio de tvoo fecha com os 150 min da etapa.
    session.add_all([
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_id,
            tvoo=60,
            reg='d',
            tipo_missao_id=tipo_id,
        ),
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_id,
            tvoo=90,
            reg='n',
            tipo_missao_id=tipo_id,
        ),
    ])
    session.add_all([
        PqdEtapa(etapa_id=etapa.id, tipo='LV', qtd=30),
        PqdEtapa(etapa_id=etapa.id, tipo='VTC', qtd=12),
    ])
    session.add(REVOEtapa(etapa_id=etapa.id, comb_transf=800))
    session.add_all([
        HeavyCDS(
            etapa_id=etapa.id, tipo='heavy', peso=2000, dist=10, radial=90
        ),
        HeavyCDS(etapa_id=etapa.id, tipo='cds', peso=300, dist=5, radial=180),
        HeavyCDS(etapa_id=etapa.id, tipo='cds', peso=400, dist=7, radial=270),
    ])
    await session.commit()
    return etapa


async def test_sem_token_401(client):
    resp = await client.get(URL, params={'ano_ref': ANO})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


async def test_sem_org_ativa_400(client, token_sistema):
    """Painel é data-plane: sem org ativa não há o que escopar."""
    resp = await client.get(
        URL, params={'ano_ref': ANO}, headers=_auth(token_sistema)
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_sem_permissao_403(client, token_sem_perm):
    """Gate `estatistica.indicadores/view` — este nasce fechado."""
    resp = await client.get(
        URL, params={'ano_ref': ANO}, headers=_auth(token_sem_perm)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_fan_out_nao_multiplica_metricas_da_etapa(
    client, token, etapa_com_filhas
):
    """Métricas da etapa não podem ser multiplicadas pelas filhas.

    Uma etapa com 2 OIs + 2 PQD + 1 REVO + 3 lançamentos. Se as
    agregações caírem num JOIN único, `carga` viraria 12.000 em vez de
    1.000 — a tela continuaria carregando, só que mentindo.
    """
    resp = await client.get(URL, params={'ano_ref': ANO}, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    totais = data['totais']

    # As métricas que MORAM na etapa: exatamente uma vez cada.
    assert totais['etapas'] == 1
    assert totais['tvoo'] == 150
    assert totais['pousos'] == 1
    assert totais['pax'] == 10
    assert totais['carga'] == 1000
    assert totais['comb'] == 500
    assert totais['lub'] == 2.5

    # As métricas que moram nas FILHAS: somadas uma vez por filha.
    assert totais['pqd'] == 42  # 30 + 12
    assert totais['comb_transf'] == 800
    assert totais['heavy_qtd'] == 1
    assert totais['cds_qtd'] == 2
    assert totais['peso_lancado'] == 2700  # 2000 + 300 + 400

    # A linha de março espelha os totais (só há uma etapa no ano).
    marco = next(m for m in data['mensal'] if m['mes'] == 3)
    assert marco['carga'] == 1000
    assert marco['pax'] == 10
    assert marco['pqd'] == 42
    assert marco['peso_lancado'] == 2700


async def test_quebra_por_oi_soma_apenas_tvoo_rateado(
    client, token, etapa_com_filhas
):
    """Regime/tipo de missão só podem somar `OIEtapa.tvoo`.

    O rateio fecha com o tvoo da etapa (60 + 90 = 150). Somar
    carga/pax agrupando por OI seria o mesmo bug de fan-out.
    """
    resp = await client.get(URL, params={'ano_ref': ANO}, headers=_auth(token))
    data = resp.json()['data']

    por_regime = {r['reg']: r['tvoo'] for r in data['por_regime']}
    assert por_regime == {'d': 60, 'n': 90}
    assert sum(por_regime.values()) == data['totais']['tvoo']

    assert len(data['por_tipo_missao']) == 1
    tipo = data['por_tipo_missao'][0]
    assert tipo['cod'] == 'ADT'
    assert tipo['tvoo'] == 150
    # A etapa é UMA, mesmo tendo dois OIs apontando para o mesmo tipo.
    assert tipo['etapas'] == 1


async def test_isolamento_cross_org(
    client, session, users, make_org_token, etapa_com_filhas, refs
):
    """Etapas da '11gt' não podem aparecer no painel da '1gt'."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    session.add(
        Aeronave(
            matricula='2860',
            active=True,
            sit='DI',
            obs=None,
            projeto='C1',
        )
    )
    missao_1gt = Missao(titulo=None, obs=None, uae='1gt')
    session.add(missao_1gt)
    await session.flush()
    await _mk_etapa(session, missao_1gt.id, anv='2860', carga=777, pax=3)
    await session.commit()

    token_1gt = await make_org_token(other, active_org='1gt')
    resp = await client.get(
        URL, params={'ano_ref': ANO}, headers=_auth(token_1gt)
    )
    assert resp.status_code == HTTPStatus.OK
    totais = resp.json()['data']['totais']

    # Só a etapa da própria org — nada da '11gt' vaza.
    assert totais['etapas'] == 1
    assert totais['carga'] == 777
    assert totais['pax'] == 3
    assert totais['pqd'] == 0
    assert totais['peso_lancado'] == 0

    anvs = {a['anv'] for a in resp.json()['data']['por_aeronave']}
    assert anvs == {'2860'}


async def test_simulador_fica_de_fora(client, session, token, refs):
    """O painel é de produção real: `is_simulador` nunca entra."""
    session.add(Aeronave(matricula='2850', active=True, sit='DI', obs=None))
    real = Missao(titulo=None, obs=None, uae='11gt')
    sim = Missao(titulo=None, obs=None, uae='11gt', is_simulador=True)
    session.add_all([real, sim])
    await session.flush()

    await _mk_etapa(session, real.id, anv='2850', carga=100)
    await _mk_etapa(session, sim.id, anv='2850', carga=9999)
    await session.commit()

    resp = await client.get(URL, params={'ano_ref': ANO}, headers=_auth(token))
    totais = resp.json()['data']['totais']
    assert totais['etapas'] == 1
    assert totais['carga'] == 100


async def test_filtro_por_projeto_discrimina(client, session, token, refs):
    """`projeto` recorta a frota; omitir devolve todos os projetos.

    Cenário deliberado: a MESMA org voa duas aeronaves de projetos
    diferentes. Sem isso o filtro passa em qualquer implementação —
    inclusive numa que ignore o parâmetro.
    """
    session.add_all([
        Aeronave(matricula='2850', active=True, sit='DI', obs=None),
        Aeronave(
            matricula='2860',
            active=True,
            sit='DI',
            obs=None,
            projeto='C1',
        ),
    ])
    missao = Missao(titulo=None, obs=None, uae='11gt')
    session.add(missao)
    await session.flush()
    await _mk_etapa(session, missao.id, anv='2850', carga=100)
    await _mk_etapa(session, missao.id, anv='2860', carga=200)
    await session.commit()

    async def _get(**params):
        resp = await client.get(
            URL, params={'ano_ref': ANO, **params}, headers=_auth(token)
        )
        assert resp.status_code == HTTPStatus.OK
        return resp.json()['data']

    todos = await _get()
    assert todos['totais']['etapas'] == 2
    assert todos['totais']['carga'] == 300

    so_c8 = await _get(projeto='C8')
    assert so_c8['totais']['etapas'] == 1
    assert so_c8['totais']['carga'] == 100
    assert {a['anv'] for a in so_c8['por_aeronave']} == {'2850'}

    so_c1 = await _get(projeto='C1')
    assert so_c1['totais']['etapas'] == 1
    assert so_c1['totais']['carga'] == 200
    assert {a['anv'] for a in so_c1['por_aeronave']} == {'2860'}


async def test_ano_vazio_devolve_doze_meses_zerados(client, token):
    """Série mensal sempre com 12 posições — o front não inventa mês."""
    resp = await client.get(
        URL, params={'ano_ref': 2024}, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']

    assert data['ano_ref'] == 2024
    assert len(data['mensal']) == 12
    assert [m['mes'] for m in data['mensal']] == list(range(1, 13))
    assert all(m['tvoo'] == 0 and m['carga'] == 0 for m in data['mensal'])

    assert data['totais']['etapas'] == 0
    assert data['por_regime'] == []
    assert data['por_tipo_missao'] == []
    assert data['por_aeronave'] == []
    assert data['lancamentos'] == []


async def test_etapa_de_outro_ano_nao_entra(client, session, token, refs):
    """Recorte anual: dezembro/ANO entra, janeiro/ANO+1 não."""
    session.add(Aeronave(matricula='2850', active=True, sit='DI', obs=None))
    missao = Missao(titulo=None, obs=None, uae='11gt')
    session.add(missao)
    await session.flush()

    await _mk_etapa(
        session, missao.id, anv='2850', data=date(ANO, 12, 31), carga=50
    )
    await _mk_etapa(
        session, missao.id, anv='2850', data=date(ANO + 1, 1, 1), carga=60
    )
    await session.commit()

    resp = await client.get(URL, params={'ano_ref': ANO}, headers=_auth(token))
    data = resp.json()['data']
    assert data['totais']['etapas'] == 1
    assert data['totais']['carga'] == 50
    assert data['mensal'][11]['carga'] == 50  # dezembro
