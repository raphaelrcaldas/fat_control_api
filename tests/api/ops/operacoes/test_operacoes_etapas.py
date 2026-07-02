"""Testes de etapas associadas a Operações.

Endpoints: listar associadas, listar candidatas, associar e desassociar.
Foco de segurança: o escopo das candidatas/associáveis vem da MISSÃO
(`Missao.uae`), então etapas de voo de outra unidade não podem ser
associadas — mesmo o admin não enxerga voos de outra org.
"""

from datetime import date, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.etapa import Etapa, Missao
from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.models.shared.operacao import OperacaoEtapa
from tests.factories import OperacaoFactory

pytestmark = pytest.mark.anyio


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _missao(session, uae):
    m = Missao(titulo=None, obs=None, uae=uae)
    session.add(m)
    await session.flush()
    return m


async def _etapa(session, missao_id, data, *, anv='2850'):
    etapa = Etapa(
        missao_id=missao_id,
        obs=None,
        data=data,
        origem='SBGL',
        destino='SBBR',
        dep=time(10, 0),
        arr=time(11, 30),
        anv=anv,
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
    session.add(etapa)
    await session.flush()
    return etapa


@pytest.fixture
async def aeronave(session):
    av = Aeronave(matricula='2850', active=True, sit='DI', obs=None)
    session.add(av)
    await session.commit()
    return av


@pytest.fixture
async def operacao(session, users):
    user, _ = users
    op = OperacaoFactory(
        created_by=user.id,
        data_inicio=date(2025, 6, 1),
        data_fim=date(2025, 6, 10),
    )
    session.add(op)
    await session.commit()
    await session.refresh(op)
    return op


# --------------------------------------------------------------------------- #
# Candidatas
# --------------------------------------------------------------------------- #
async def test_candidatas_scoped_by_missao_org(
    client, session, aeronave, operacao, org_admin_token
):
    """Candidatas só trazem etapas de missões da org ativa ('11gt')."""
    m_org = await _missao(session, '11gt')
    m_outra = await _missao(session, '1gt')
    e_org = await _etapa(session, m_org.id, date(2025, 6, 5))
    await _etapa(session, m_outra.id, date(2025, 6, 5))
    await session.commit()

    resp = await client.get(
        f'/ops/operacoes/{operacao.id}/candidatas',
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK
    ids = [c['id'] for c in resp.json()['data']]
    assert ids == [e_org.id]


async def test_candidatas_excludes_out_of_period(
    client, session, aeronave, operacao, org_admin_token
):
    m = await _missao(session, '11gt')
    e_dentro = await _etapa(session, m.id, date(2025, 6, 5))
    await _etapa(session, m.id, date(2025, 12, 31))
    await session.commit()

    resp = await client.get(
        f'/ops/operacoes/{operacao.id}/candidatas',
        headers=_auth(org_admin_token),
    )
    ids = [c['id'] for c in resp.json()['data']]
    assert ids == [e_dentro.id]


# --------------------------------------------------------------------------- #
# Associar
# --------------------------------------------------------------------------- #
async def test_associar_success(
    client, session, aeronave, operacao, org_admin_token
):
    m = await _missao(session, '11gt')
    etapa = await _etapa(session, m.id, date(2025, 6, 5))
    await session.commit()

    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/etapas',
        json={'etapa_ids': [etapa.id]},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['associadas'] == 1
    assert data['bloqueadas'] == []

    lst = await client.get(
        f'/ops/operacoes/{operacao.id}/etapas',
        headers=_auth(org_admin_token),
    )
    assert [e['id'] for e in lst.json()['data']] == [etapa.id]


async def test_associar_rejects_other_org_etapa(
    client, session, aeronave, operacao, org_admin_token
):
    """Etapa de missão de outra org não é associada (escopo via missão)."""
    m_outra = await _missao(session, '1gt')
    etapa = await _etapa(session, m_outra.id, date(2025, 6, 5))
    await session.commit()

    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/etapas',
        json={'etapa_ids': [etapa.id]},
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['associadas'] == 0


async def test_associar_blocks_etapa_in_other_op(
    client, session, users, aeronave, operacao, org_admin_token
):
    """Etapa já vinculada a outra operação entra em `bloqueadas`."""
    user, _ = users
    outra_op = OperacaoFactory(
        created_by=user.id,
        data_inicio=date(2025, 6, 1),
        data_fim=date(2025, 6, 10),
    )
    session.add(outra_op)
    await session.flush()

    m = await _missao(session, '11gt')
    etapa = await _etapa(session, m.id, date(2025, 6, 5))
    session.add(OperacaoEtapa(etapa_id=etapa.id, operacao_id=outra_op.id))
    await session.commit()

    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/etapas',
        json={'etapa_ids': [etapa.id]},
        headers=_auth(org_admin_token),
    )
    data = resp.json()['data']
    assert data['associadas'] == 0
    assert data['bloqueadas'] == [etapa.id]


async def test_associar_viewer_forbidden(
    client, session, aeronave, operacao, oper_viewer_token
):
    m = await _missao(session, '11gt')
    etapa = await _etapa(session, m.id, date(2025, 6, 5))
    await session.commit()

    resp = await client.post(
        f'/ops/operacoes/{operacao.id}/etapas',
        json={'etapa_ids': [etapa.id]},
        headers=_auth(oper_viewer_token),
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


# --------------------------------------------------------------------------- #
# Desassociar
# --------------------------------------------------------------------------- #
async def test_desassociar_success(
    client, session, aeronave, operacao, org_admin_token
):
    m = await _missao(session, '11gt')
    etapa = await _etapa(session, m.id, date(2025, 6, 5))
    session.add(OperacaoEtapa(etapa_id=etapa.id, operacao_id=operacao.id))
    await session.commit()

    resp = await client.delete(
        f'/ops/operacoes/{operacao.id}/etapas/{etapa.id}',
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.OK

    lst = await client.get(
        f'/ops/operacoes/{operacao.id}/etapas',
        headers=_auth(org_admin_token),
    )
    assert lst.json()['data'] == []


async def test_desassociar_not_associated_404(
    client, session, aeronave, operacao, org_admin_token
):
    m = await _missao(session, '11gt')
    etapa = await _etapa(session, m.id, date(2025, 6, 5))
    await session.commit()

    resp = await client.delete(
        f'/ops/operacoes/{operacao.id}/etapas/{etapa.id}',
        headers=_auth(org_admin_token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
