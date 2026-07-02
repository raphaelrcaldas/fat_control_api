"""Testes do endpoint GET /esfaer/ (resumo).

Resumo anual de Esforço Aéreo por programa (alocado SAGEM x voado nas
etapas) e a flag `simulador`: quando False, os programas de simulador
(descrição contendo 'SML') saem dos itens E de todos os totais — o
cálculo é responsabilidade do backend, o front apenas exibe.
"""

from datetime import date, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.esf_aer import (
    EsfAerAloc,
    EsforcoAereo,
)
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
)
from fcontrol_api.models.shared.aeronaves import Aeronave

pytestmark = pytest.mark.anyio

URL = '/estatistica/esfaer/'
ANO = 2025


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _programa(
    session,
    *,
    grupo='COMPREP',
    prog='PRPO',
    sub_prog=None,
    aplicacao=None,
):
    esf = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo=grupo,
        prog=prog,
        sub_prog=sub_prog,
        aplicacao=aplicacao,
    )
    session.add(esf)
    await session.flush()
    return esf


async def _aloc(
    session,
    esfaer_id,
    *,
    alocado,
    meses=None,
    ano_ref=ANO,
    uae='11gt',
):
    meses = meses or [0] * 12
    aloc = EsfAerAloc(
        esfaer_id=esfaer_id,
        ano_ref=ano_ref,
        uae=uae,
        alocado=alocado,
        **{f'm{i + 1}': meses[i] for i in range(12)},
    )
    session.add(aloc)
    await session.flush()
    return aloc


@pytest.fixture
async def tipo_missao(session):
    """Aeronave e TipoMissao mínimos para compor etapas voadas."""
    session.add(Aeronave(matricula='2850', active=True, sit='DI', obs=None))
    tipo = TipoMissao(cod='ADT', desc='Adestramento')
    session.add(tipo)
    await session.flush()
    return tipo


async def _voado(
    session,
    esf_aer_id,
    *,
    tvoo,
    mes,
    tipo_missao_id,
    uae='11gt',
    ano=ANO,
):
    """Cria Missao -> Etapa -> OIEtapa com `tvoo` no mês/ano dados."""
    missao = Missao(titulo=None, obs=None, uae=uae)
    session.add(missao)
    await session.flush()

    etapa = Etapa(
        missao_id=missao.id,
        obs=None,
        data=date(ano, mes, 10),
        origem='SBGL',
        destino='SBGL',
        dep=time(10, 0),
        arr=time(11, 0),
        anv='2850',
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

    session.add(
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_aer_id,
            tvoo=tvoo,
            reg='d',
            tipo_missao_id=tipo_missao_id,
        )
    )
    await session.flush()


async def _get(client, token, ano_ref=ANO, simulador=None):
    params = {'ano_ref': ano_ref}
    if simulador is not None:
        params['simulador'] = simulador
    resp = await client.get(URL, params=params, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    return resp.json()['data']


async def test_default_inclui_simulador(client, session, org_token):
    """Sem a flag, programas SML entram nos itens e nos totais; passar
    `simulador=true` explícito (como o front envia) é equivalente."""
    normal = await _programa(session)
    sml = await _programa(session, sub_prog='SML')
    await _aloc(session, normal.id, alocado=100)
    await _aloc(session, sml.id, alocado=50, meses=[50] + [0] * 11)
    await session.commit()

    data = await _get(client, org_token)

    descricoes = {i['descricao'] for i in data['items']}
    assert descricoes == {'COMPREP PRPO', 'COMPREP PRPO SML'}
    assert data['total_alocado'] == 150
    assert data['total_saldo'] == 150
    assert data['total_meses_sagem'][0] == 50

    data_true = await _get(client, org_token, simulador=True)
    assert data_true == data


async def test_simulador_false_exclui_sml_itens_e_totais(
    client, session, org_token, tipo_missao
):
    """Com simulador=false o programa SML sai dos itens e de TODOS os
    totais (alocado, voado, saldo e séries mensais) — nada é subtraído
    no front."""
    normal = await _programa(session)
    sml = await _programa(session, sub_prog='SML')
    await _aloc(session, normal.id, alocado=100)
    await _aloc(session, sml.id, alocado=50, meses=[50] + [0] * 11)
    await _voado(
        session, normal.id, tvoo=60, mes=3, tipo_missao_id=tipo_missao.id
    )
    await _voado(
        session, sml.id, tvoo=30, mes=3, tipo_missao_id=tipo_missao.id
    )
    await session.commit()

    data = await _get(client, org_token, simulador=False)

    assert [i['descricao'] for i in data['items']] == ['COMPREP PRPO']
    item = data['items'][0]
    assert item['alocado'] == 100
    assert item['voado'] == 60
    assert item['saldo'] == 40
    assert data['total_alocado'] == 100
    assert data['total_voado'] == 60
    assert data['total_saldo'] == 40
    assert data['total_meses_voados'][2] == 60
    assert data['total_meses_sagem'] == [0] * 12

    # Default (sem flag) soma também o simulador
    data_all = await _get(client, org_token)
    assert data_all['total_alocado'] == 150
    assert data_all['total_voado'] == 90
    assert data_all['total_saldo'] == 60
    assert data_all['total_meses_voados'][2] == 90


async def test_item_so_voado_sem_alocacao(
    client, session, org_token, tipo_missao
):
    """Programa SML sem alocação mas com voo aparece por default (saldo
    negativo) e some com simulador=false."""
    sml = await _programa(session, sub_prog='SML')
    await _voado(
        session, sml.id, tvoo=30, mes=5, tipo_missao_id=tipo_missao.id
    )
    await session.commit()

    data = await _get(client, org_token)
    assert len(data['items']) == 1
    assert data['items'][0]['alocado'] == 0
    assert data['items'][0]['voado'] == 30
    assert data['items'][0]['saldo'] == -30

    data_sem = await _get(client, org_token, simulador=False)
    assert data_sem['items'] == []
    assert data_sem['total_voado'] == 0
    assert data_sem['total_saldo'] == 0


async def test_org_sem_dados(client, org_token):
    """Org sem alocações/voos: itens vazios e totais zerados."""
    data = await _get(client, org_token, simulador=False)

    assert data['items'] == []
    assert data['total_alocado'] == 0
    assert data['total_voado'] == 0
    assert data['total_saldo'] == 0
    assert data['total_meses_sagem'] == [0] * 12
    assert data['total_meses_voados'] == [0] * 12


async def test_isolamento_por_org_e_ano(client, session, org_token):
    """Alocações de outra org (`uae != active_org`) e de outro `ano_ref`
    não entram no resumo."""
    esf = await _programa(session)
    await _aloc(session, esf.id, alocado=100)  # 11gt / 2025 (visível)
    await _aloc(session, esf.id, alocado=500, uae='1gt')  # outra org
    await _aloc(session, esf.id, alocado=700, ano_ref=2024)  # outro ano
    await session.commit()

    data = await _get(client, org_token)

    assert len(data['items']) == 1
    assert data['total_alocado'] == 100
