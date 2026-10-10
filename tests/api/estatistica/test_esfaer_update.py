"""Testes do endpoint PUT /esfaer/ (importação do Esforço Aéreo).

A importação é substituição total do ano da org ativa: o que veio no texto é
criado ou atualizado, o que não veio é zerado. O catálogo `EsforcoAereo` é
compartilhado entre unidades; só as alocações (`EsfAerAloc`) são por unidade.
Cada mudança de valor grava em `EsfAerAlocHist` o valor ANTERIOR — é dele que
o histórico reconstrói a timeline.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.estatistica.esf_aer import (
    EsfAerAloc,
    EsfAerAlocHist,
    EsforcoAereo,
)

pytestmark = pytest.mark.anyio

URL = '/estatistica/esfaer/'
ANO = 2025


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _item(*, prog='PRPO', sub_prog='', horas=0, meses=None, grupo='COMPREP'):
    return {
        'tipo': 'AVIAO',
        'modelo': 'C-105',
        'grupo': grupo,
        'programa': prog,
        'subprograma': sub_prog,
        'aplicacao': '',
        'horas_alocadas': horas,
        'meses_sagem': meses or [0] * 12,
    }


async def _programa(session, *, prog='PRPO', sub_prog=None):
    esf = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo='COMPREP',
        prog=prog,
        sub_prog=sub_prog,
        aplicacao=None,
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
        **{f'm{i}': alocado // 12 // 5 * 5 for i in range(1, 13)},
    )
    session.add(aloc)
    await session.flush()
    return aloc


async def _put(client, token, items, ano_ref=ANO):
    resp = await client.put(
        URL,
        json={'ano_ref': ano_ref, 'items': items},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK, resp.json()
    return resp.json()['data']


async def _hists(session, aloc_id):
    return (
        await session.scalars(
            select(EsfAerAlocHist.aloc_hist)
            .where(EsfAerAlocHist.esf_aer_aloc_id == aloc_id)
            .order_by(EsfAerAlocHist.id)
        )
    ).all()


async def test_put_cria_programa_e_alocacao(client, session, token):
    """Programa fora do catálogo nasce no catálogo e com alocação na org
    ativa; o histórico registra o "nada alocado" anterior (0)."""
    meses = [10, 20] + [0] * 10

    data = await _put(client, token, [_item(horas=100, meses=meses)])

    assert data['rows'] == [
        {'descricao': 'COMPREP PRPO', 'antes': None, 'depois': 100}
    ]
    assert data['total_antes'] == 0
    assert data['total_depois'] == 100

    aloc = await session.scalar(
        select(EsfAerAloc)
        .join(EsforcoAereo, EsforcoAereo.id == EsfAerAloc.esfaer_id)
        .where(EsforcoAereo.prog == 'PRPO')
        .execution_options(populate_existing=True)
    )
    assert (aloc.uae, aloc.ano_ref, aloc.alocado) == ('11gt', ANO, 100)
    assert [getattr(aloc, f'm{i}') for i in range(1, 13)] == meses
    assert await _hists(session, aloc.id) == [0]


async def test_put_atualiza_existente_grava_valor_anterior(
    client, session, token
):
    """Chave igual (com espaços em volta, que são aparados) atualiza a
    alocação existente — valor e distribuição mensal — em vez de criar outro
    programa no catálogo."""
    esf = await _programa(session)
    aloc = await _aloc(session, esf.id, alocado=100)
    await session.commit()

    meses = [0, 0, 50, 100] + [0] * 8
    item = _item(horas=150, meses=meses)
    item['grupo'] = '  COMPREP '
    data = await _put(client, token, [item])

    assert data['rows'] == [
        {'descricao': 'COMPREP PRPO', 'antes': 100, 'depois': 150}
    ]
    assert data['total_antes'] == 100
    assert data['total_depois'] == 150

    await session.refresh(aloc)
    assert aloc.alocado == 150
    assert [getattr(aloc, f'm{i}') for i in range(1, 13)] == meses
    assert await _hists(session, aloc.id) == [100]
    catalogo = await session.scalar(
        select(func.count()).select_from(EsforcoAereo)
    )
    assert catalogo == 1


async def test_put_programa_do_catalogo_sem_alocacao_na_org(
    client, session, token
):
    """Programa que já está no catálogo (criado por outra org ou em outro
    ano) ganha alocação PRÓPRIA da org ativa no ano — a da outra org não é
    reaproveitada nem alterada. É o caso de importar um ano novo."""
    esf = await _programa(session)
    alheia = await _aloc(session, esf.id, alocado=300, uae='1gt')
    anterior = await _aloc(session, esf.id, alocado=400, ano_ref=ANO - 1)
    await session.commit()

    data = await _put(client, token, [_item(horas=100)])

    assert data['rows'] == [
        {'descricao': 'COMPREP PRPO', 'antes': None, 'depois': 100}
    ]
    nova = await session.scalar(
        select(EsfAerAloc)
        .where(
            EsfAerAloc.esfaer_id == esf.id,
            EsfAerAloc.uae == '11gt',
            EsfAerAloc.ano_ref == ANO,
        )
        .execution_options(populate_existing=True)
    )
    assert nova.alocado == 100
    assert await _hists(session, nova.id) == [0]

    for aloc in (alheia, anterior):
        await session.refresh(aloc)
    assert alheia.alocado == 300
    assert anterior.alocado == 400


async def test_put_zera_ausentes_so_da_org_ativa_e_do_ano(
    client, session, token
):
    """O programa que não veio no texto é zerado (alocado e meses) na org e
    no ano importados; a alocação de outra org e a de outro ano do mesmo
    programa ficam intactas."""
    mantido = await _programa(session)
    ausente = await _programa(session, prog='PRAA')
    await _aloc(session, mantido.id, alocado=100)
    zerada = await _aloc(session, ausente.id, alocado=240)
    outra_org = await _aloc(session, ausente.id, alocado=300, uae='1gt')
    outro_ano = await _aloc(session, ausente.id, alocado=400, ano_ref=2024)
    await session.commit()

    data = await _put(client, token, [_item(horas=100)])

    assert data['rows'] == [
        {'descricao': 'COMPREP PRAA', 'antes': 240, 'depois': None}
    ]
    assert data['total_antes'] == 340
    assert data['total_depois'] == 100

    for aloc in (zerada, outra_org, outro_ano):
        await session.refresh(aloc)
    assert zerada.alocado == 0
    assert [getattr(zerada, f'm{i}') for i in range(1, 13)] == [0] * 12
    assert await _hists(session, zerada.id) == [240]

    assert outra_org.alocado == 300
    assert outro_ano.alocado == 400
    assert await _hists(session, outra_org.id) == []
    assert await _hists(session, outro_ano.id) == []


async def test_put_sem_mudanca_nao_grava_historico(client, session, token):
    """Reimportar o mesmo valor, ou criar um programa em 0, não é mudança:
    nada vai para o histórico nem para as linhas do diff."""
    esf = await _programa(session)
    aloc = await _aloc(session, esf.id, alocado=100)
    await session.commit()

    data = await _put(
        client, token, [_item(horas=100), _item(prog='PRZZ', horas=0)]
    )

    assert data['rows'] == []
    assert data['total_antes'] == data['total_depois'] == 100
    assert await _hists(session, aloc.id) == []
    nova = await session.scalar(
        select(EsfAerAloc)
        .join(EsforcoAereo, EsforcoAereo.id == EsfAerAloc.esfaer_id)
        .where(EsforcoAereo.prog == 'PRZZ')
    )
    assert nova.alocado == 0
    assert await _hists(session, nova.id) == []


async def test_put_totais_excluem_simulador(client, session, token):
    """Programa de simulador ('SML' na descrição) entra no diff e no
    histórico, mas fica fora dos totais antes/depois."""
    sml = await _programa(session, sub_prog='SML')
    aloc_sml = await _aloc(session, sml.id, alocado=50)
    await session.commit()

    data = await _put(
        client,
        token,
        [_item(sub_prog='SML', horas=80), _item(horas=100)],
    )

    assert {r['descricao'] for r in data['rows']} == {
        'COMPREP PRPO',
        'COMPREP PRPO SML',
    }
    assert data['total_antes'] == 0
    assert data['total_depois'] == 100
    assert await _hists(session, aloc_sml.id) == [50]


async def test_put_itens_duplicados_422(client, session, token):
    """A mesma chave duas vezes no texto — mesmo diferindo só em espaços,
    que o schema apara — é recusada antes de tocar o banco; senão a segunda
    linha sobrescreveria a primeira em silêncio."""
    resp = await client.put(
        URL,
        json={
            'ano_ref': ANO,
            'items': [_item(horas=10), _item(prog=' PRPO ', horas=20)],
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'duplicados' in resp.text
    catalogo = await session.scalar(
        select(func.count()).select_from(EsforcoAereo)
    )
    assert catalogo == 0
