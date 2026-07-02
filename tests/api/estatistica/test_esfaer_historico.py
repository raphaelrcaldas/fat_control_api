"""Testes do endpoint GET /esfaer/historico.

Reconstrução da timeline de alocações de Esforço Aéreo por programa
(step-function a partir de `EsfAerAlocHist`, que guarda o valor ANTERIOR
a cada mudança) e da série agregada (carry-forward) da org ativa.
"""

from datetime import datetime
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.esf_aer import (
    EsfAerAloc,
    EsfAerAlocHist,
    EsforcoAereo,
)

pytestmark = pytest.mark.anyio

URL = '/estatistica/esfaer/historico'
ANO = 2025


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _programa(
    session,
    *,
    grupo='INSTRUCAO',
    prog='PROG-A',
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


async def _aloc(session, esfaer_id, *, alocado, ano_ref=ANO, uae='11gt'):
    aloc = EsfAerAloc(
        esfaer_id=esfaer_id,
        ano_ref=ano_ref,
        uae=uae,
        alocado=alocado,
    )
    session.add(aloc)
    await session.flush()
    return aloc


async def _hist(session, aloc_id, aloc_hist, ts):
    hist = EsfAerAlocHist(
        esf_aer_aloc_id=aloc_id,
        aloc_hist=aloc_hist,
        timestamp=ts,
    )
    session.add(hist)
    await session.flush()
    return hist


async def _get(client, token, ano_ref=ANO):
    resp = await client.get(
        URL, params={'ano_ref': ano_ref}, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.OK
    return resp.json()['data']


async def test_programa_sem_hist_timeline_vazia(client, session, org_token):
    """Programa sem histórico aparece com `atual` e timeline vazia."""
    esf = await _programa(session)
    await _aloc(session, esf.id, alocado=100)
    await session.commit()

    data = await _get(client, org_token)

    assert data['ano_ref'] == ANO
    assert len(data['programas']) == 1
    programa = data['programas'][0]
    assert programa['esfaer_id'] == esf.id
    assert programa['atual'] == 100
    assert programa['timeline'] == []
    # Sem hists não há datas: total só tem o valor atual
    assert data['total']['atual'] == 100
    assert data['total']['timeline'] == []


async def test_programa_com_um_hist_criacao(client, session, org_token):
    """Criação (hist com valor anterior 0) colapsa base + mudança no dia.

    O primeiro ponto tem a data do timestamp e, como a mudança ocorre no
    mesmo dia do ponto-base, o valor exibido é o vigente (alocado) com
    delta = alocado - aloc_hist.
    """
    esf = await _programa(session)
    aloc = await _aloc(session, esf.id, alocado=150)
    await _hist(session, aloc.id, 0, datetime(2025, 2, 10, 14, 30))
    await session.commit()

    data = await _get(client, org_token)

    programa = data['programas'][0]
    assert programa['atual'] == 150
    assert programa['timeline'] == [
        {'data': '2025-02-10', 'alocado': 150, 'delta': 150},
    ]


async def test_step_function_multiplas_revisoes(client, session, org_token):
    """N revisões: valor entre h_i e h_{i+1} é h_{i+1}.aloc_hist; após a
    última o valor é `alocado`. Deltas assinados e ordenação ascendente."""
    esf = await _programa(session)
    aloc = await _aloc(session, esf.id, alocado=80)
    # 100 -> 200 (mar/01), 200 -> 50 (mai/15), 50 -> 80 (ago/20)
    await _hist(session, aloc.id, 100, datetime(2025, 3, 1, 9, 0))
    await _hist(session, aloc.id, 200, datetime(2025, 5, 15, 9, 0))
    await _hist(session, aloc.id, 50, datetime(2025, 8, 20, 9, 0))
    await session.commit()

    data = await _get(client, org_token)

    programa = data['programas'][0]
    assert programa['atual'] == 80
    assert programa['timeline'] == [
        {'data': '2025-03-01', 'alocado': 200, 'delta': 100},
        {'data': '2025-05-15', 'alocado': 50, 'delta': -150},
        {'data': '2025-08-20', 'alocado': 80, 'delta': 30},
    ]


async def test_mudancas_no_mesmo_dia_colapsam(client, session, org_token):
    """Várias mudanças no mesmo dia geram um único ponto com o último
    valor vigente do dia."""
    esf = await _programa(session)
    aloc = await _aloc(session, esf.id, alocado=300)
    # Mesmo dia: 100 -> 500 -> 300 (valor final da tabela)
    await _hist(session, aloc.id, 100, datetime(2025, 4, 2, 8, 0))
    await _hist(session, aloc.id, 500, datetime(2025, 4, 2, 16, 0))
    await session.commit()

    data = await _get(client, org_token)

    programa = data['programas'][0]
    assert programa['timeline'] == [
        {'data': '2025-04-02', 'alocado': 300, 'delta': 200},
    ]


async def test_total_carry_forward(client, session, org_token):
    """Total agrega os valores vigentes de todos os programas em cada
    data da união; programa sem hist contribui com `atual` constante."""
    # Programa A: 100 -> 200 em mar/01, 200 -> 250 em jul/10
    esf_a = await _programa(session, prog='PROG-A')
    aloc_a = await _aloc(session, esf_a.id, alocado=250)
    await _hist(session, aloc_a.id, 100, datetime(2025, 3, 1, 9, 0))
    await _hist(session, aloc_a.id, 200, datetime(2025, 7, 10, 9, 0))

    # Programa B: 50 -> 30... (30 é o alocado atual); mudança em mai/05
    esf_b = await _programa(session, prog='PROG-B')
    aloc_b = await _aloc(session, esf_b.id, alocado=30)
    await _hist(session, aloc_b.id, 50, datetime(2025, 5, 5, 9, 0))

    # Programa C: sem hist, contribui com 40 constante
    esf_c = await _programa(session, prog='PROG-C')
    await _aloc(session, esf_c.id, alocado=40)
    await session.commit()

    data = await _get(client, org_token)

    assert data['total']['atual'] == 250 + 30 + 40
    # Datas da união: mar/01 (A), mai/05 (B), jul/10 (A)
    # mar/01: A=200, B=50 (inicial), C=40  -> 290
    # mai/05: A=200, B=30,           C=40  -> 270
    # jul/10: A=250, B=30,           C=40  -> 320
    # Delta do 1º ponto é 0 (base = valor do próprio 1º ponto)
    assert data['total']['timeline'] == [
        {'data': '2025-03-01', 'alocado': 290, 'delta': 0},
        {'data': '2025-05-05', 'alocado': 270, 'delta': -20},
        {'data': '2025-07-10', 'alocado': 320, 'delta': 50},
    ]


async def test_isolamento_por_org_e_ano(client, session, org_token):
    """Alocações de outra org (`uae != active_org`) e de outro `ano_ref`
    não aparecem na resposta."""
    esf = await _programa(session)
    await _aloc(session, esf.id, alocado=100)  # 11gt / 2025 (visível)
    await _aloc(session, esf.id, alocado=500, uae='1gt')  # outra org
    await _aloc(session, esf.id, alocado=700, ano_ref=2024)  # outro ano
    await session.commit()

    data = await _get(client, org_token)

    assert len(data['programas']) == 1
    assert data['programas'][0]['atual'] == 100
    assert data['total']['atual'] == 100


async def test_programa_zerado_com_hist_entra(client, session, org_token):
    """Programa com alocado=0 (removido) e histórico entra na resposta."""
    esf = await _programa(session)
    aloc = await _aloc(session, esf.id, alocado=0)
    await _hist(session, aloc.id, 150, datetime(2025, 6, 1, 9, 0))
    await session.commit()

    data = await _get(client, org_token)

    assert len(data['programas']) == 1
    programa = data['programas'][0]
    assert programa['atual'] == 0
    assert programa['timeline'] == [
        {'data': '2025-06-01', 'alocado': 0, 'delta': -150},
    ]


async def test_nome_derivado_e_grupo(client, session, org_token):
    """`nome` usa aplicacao ?? sub_prog ?? prog; `grupo` é string livre."""
    esf_prog = await _programa(session, grupo='ADESTR', prog='SO-PROG')
    esf_sub = await _programa(
        session, grupo='EMPREGO', prog='PROG-S', sub_prog='SUBPROG'
    )
    esf_apl = await _programa(
        session,
        grupo='APOIO',
        prog='PROG-P',
        sub_prog='SUB-P',
        aplicacao='APLIC',
    )
    for esf in (esf_prog, esf_sub, esf_apl):
        await _aloc(session, esf.id, alocado=10)
    await session.commit()

    data = await _get(client, org_token)

    por_id = {p['esfaer_id']: p for p in data['programas']}
    assert por_id[esf_prog.id]['nome'] == 'SO-PROG'
    assert por_id[esf_prog.id]['grupo'] == 'ADESTR'
    assert por_id[esf_sub.id]['nome'] == 'SUBPROG'
    assert por_id[esf_apl.id]['nome'] == 'APLIC'
    assert por_id[esf_apl.id]['grupo'] == 'APOIO'
