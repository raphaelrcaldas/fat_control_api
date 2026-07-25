"""
Testes de auditoria (UserActionLog) das rotas de Ordem de Missao.

Cobrem o que o snapshot rico (`ordem_snapshot`) promete: create/update/
delete de OM sob o recurso `ordem_missao`, o CRUD de etiqueta sob o
recurso proprio `om_etiqueta` e o silencio do update que nao muda nada.

O foco aqui e o *conteudo* do before/after — as listas (etapas,
tripulacao, etiquetas) sao a parte fragil, porque as colecoes do objeto
`ordem` ficam stale depois que o endpoint recria as linhas.
"""

import json
from datetime import timezone
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.om import Etiqueta, OrdemEtapa

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om/'
ETIQUETAS_URL = '/ops/om/etiquetas/'

RESOURCE = 'ordem_missao'
RESOURCE_ETIQUETA = 'om_etiqueta'


def _make_etapa(
    dt_dep='2025-06-15T10:00:00',
    dt_arr='2025-06-15T11:30:00',
    origem='SBGL',
    dest='SBBR',
    alternativa='SBCF',
    tvoo_alt=30,
    qtd_comb=15,
    esf_aer='normal',
):
    """Helper para criar payload de etapa (90 min de voo no default)."""
    return {
        'dt_dep': dt_dep,
        'origem': origem,
        'dest': dest,
        'dt_arr': dt_arr,
        'alternativa': alternativa,
        'tvoo_alt': tvoo_alt,
        'qtd_comb': qtd_comb,
        'esf_aer': esf_aer,
    }


def _make_ordem_payload(etapas=None, etiquetas_ids=None, tripulacao=None):
    """Helper para criar payload de ordem."""
    return {
        'matricula_anv': '2850',
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'esf_aer': 240,
        'campos_especiais': [],
        'etapas': etapas if etapas is not None else [],
        'tripulacao': tripulacao,
        'etiquetas_ids': etiquetas_ids or [],
    }


async def _logs(session, resource, action=None, resource_id=None):
    """Logs gravados para um recurso, em ordem de gravacao."""
    stmt = select(UserActionLog).where(UserActionLog.resource == resource)
    if action is not None:
        stmt = stmt.where(UserActionLog.action == action)
    if resource_id is not None:
        stmt = stmt.where(UserActionLog.resource_id == resource_id)

    result = await session.scalars(stmt.order_by(UserActionLog.id))
    return list(result.all())


async def _criar_ordem(client, token, **kwargs):
    """Cria uma OM pelo endpoint e devolve o payload de resposta."""
    response = await client.post(
        BASE_URL,
        json=_make_ordem_payload(**kwargs),
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.CREATED
    return response.json()['data']


# ===============================================================
# POST /ops/om/ - create
# ===============================================================


async def test_create_ordem_loga_snapshot_completo(
    client, session, users, trips, token
):
    """Create grava o log com as listas, nao so os escalares."""
    user, _ = users
    trip, _ = trips

    etiqueta = Etiqueta(
        nome='Prioridade', cor='#FF0000', descricao='alta', uae='11gt'
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)

    data = await _criar_ordem(
        client,
        token,
        etapas=[_make_etapa()],
        etiquetas_ids=[etiqueta.id],
        tripulacao={'pil': [trip.id]},
    )

    logs = await _logs(session, RESOURCE, action='create')
    assert len(logs) == 1

    log = logs[0]
    assert log.user_id == user.id
    assert log.resource_id == data['id']
    assert log.before is None

    after = json.loads(log.after)
    assert after['tipo'] == 'instrucao'
    assert after['status'] == 'rascunho'
    assert after['matricula_anv'] == '2850'
    assert after['esf_aer'] == 240
    assert after['etiquetas'] == ['Prioridade']

    # A etapa vem do payload (naive), mas o instante logado tem que ser o
    # mesmo que o banco persistiu — e o driver interpreta naive como hora
    # local, nao UTC.
    etapa_db = await session.scalar(
        select(OrdemEtapa).where(OrdemEtapa.ordem_id == data['id'])
    )
    assert after['etapas'] == [
        {
            'dt_dep': etapa_db.dt_dep.astimezone(timezone.utc).isoformat(),
            'dt_arr': etapa_db.dt_arr.astimezone(timezone.utc).isoformat(),
            'origem': 'SBGL',
            'dest': 'SBBR',
            'alternativa': 'SBCF',
            'tvoo_etp': 90,
            'tvoo_alt': 30,
            'qtd_comb': 15,
            'esf_aer': 'normal',
        }
    ]
    # Tripulacao vem do retorno do batch: a colecao do `ordem` esta stale
    # nesse ponto e deixaria a lista vazia.
    assert after['tripulacao'] == [
        {
            'funcao': 'pil',
            'tripulante_id': trip.id,
            'p_g': user.p_g,
            'nome': user.nome_guerra.upper(),
        }
    ]


async def test_create_ordem_sem_doc_ref_omite_a_chave(
    client, session, token
):
    """`doc_ref` em branco nao entra no snapshot (evita ruido)."""
    await _criar_ordem(client, token)

    logs = await _logs(session, RESOURCE, action='create')
    after = json.loads(logs[0].after)
    assert 'doc_ref' not in after


async def test_create_ordem_com_doc_ref_entra_no_snapshot(
    client, session, token
):
    """`doc_ref` preenchido entra no snapshot."""
    payload = _make_ordem_payload()
    payload['doc_ref'] = 'OFICIO-42'

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.CREATED

    logs = await _logs(session, RESOURCE, action='create')
    assert json.loads(logs[0].after)['doc_ref'] == 'OFICIO-42'


# ===============================================================
# PUT /ops/om/{id} - update
# ===============================================================


async def test_update_ordem_loga_before_e_after(client, session, token):
    """Update de campo simples grava os dois lados do diff."""
    data = await _criar_ordem(client, token)

    response = await client.put(
        f'{BASE_URL}{data["id"]}',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE, action='update')
    assert len(logs) == 1
    assert json.loads(logs[0].before)['tipo'] == 'instrucao'
    assert json.loads(logs[0].after)['tipo'] == 'transporte'


async def test_update_ordem_sem_mudanca_nao_loga(client, session, token):
    """Reenviar os mesmos dados nao gera log.

    Guarda contra a assimetria de serializacao: o `before` le as etapas
    ja gravadas (aware, UTC) e o `after` le as do payload (naive). Sem a
    normalizacao de `_iso_utc` — ou sem calcular `tvoo_etp` dos dois
    lados — todo update pareceria ter mudado.
    """
    etapa = _make_etapa()
    data = await _criar_ordem(client, token, etapas=[etapa])

    response = await client.put(
        f'{BASE_URL}{data["id"]}',
        json={
            'tipo': 'instrucao',
            'esf_aer': 240,
            'etapas': [etapa],
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    assert await _logs(session, RESOURCE, action='update') == []


async def test_update_tripulacao_entra_no_diff(
    client, session, users, trips, token
):
    """Tripulacao nova aparece no `after` (vem do retorno do batch)."""
    user, _ = users
    trip, _ = trips

    data = await _criar_ordem(client, token)

    response = await client.put(
        f'{BASE_URL}{data["id"]}',
        json={'tripulacao': {'pil': [trip.id]}},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE, action='update')
    assert len(logs) == 1
    assert json.loads(logs[0].before)['tripulacao'] == []
    assert json.loads(logs[0].after)['tripulacao'] == [
        {
            'funcao': 'pil',
            'tripulante_id': trip.id,
            'p_g': user.p_g,
            'nome': user.nome_guerra.upper(),
        }
    ]


async def test_update_etapas_removidas_entram_no_diff(
    client, session, token
):
    """Trocar a lista de etapas aparece nos dois lados do diff."""
    data = await _criar_ordem(client, token, etapas=[_make_etapa()])

    response = await client.put(
        f'{BASE_URL}{data["id"]}',
        json={'etapas': []},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE, action='update')
    assert len(logs) == 1
    assert len(json.loads(logs[0].before)['etapas']) == 1
    assert json.loads(logs[0].after)['etapas'] == []


async def test_update_cancelamento_loga(client, session, token):
    """Cancelamento (early return do endpoint) tambem grava log."""
    data = await _criar_ordem(client, token, etapas=[_make_etapa()])

    # A maquina de estados so permite cancelar o que ja foi aprovado.
    aprovacao = await client.put(
        f'{BASE_URL}{data["id"]}',
        json={'status': 'aprovada'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert aprovacao.status_code == HTTPStatus.OK

    response = await client.put(
        f'{BASE_URL}{data["id"]}',
        json={'status': 'cancelada'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE, action='update')
    assert len(logs) == 2
    assert json.loads(logs[-1].before)['status'] == 'aprovada'
    assert json.loads(logs[-1].after)['status'] == 'cancelada'


# ===============================================================
# DELETE /ops/om/{id} - delete
# ===============================================================


async def test_delete_ordem_loga_snapshot_anterior(
    client, session, users, trips, token
):
    """Soft delete guarda o estado completo em `before` e nada em `after`."""
    trip, _ = trips

    data = await _criar_ordem(
        client,
        token,
        etapas=[_make_etapa()],
        tripulacao={'pil': [trip.id]},
    )

    response = await client.delete(
        f'{BASE_URL}{data["id"]}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE, action='delete')
    assert len(logs) == 1
    assert logs[0].resource_id == data['id']
    assert logs[0].after is None

    before = json.loads(logs[0].before)
    assert before['status'] == 'rascunho'
    assert len(before['etapas']) == 1
    assert len(before['tripulacao']) == 1


# ===============================================================
# /ops/om/etiquetas/ - CRUD sob recurso proprio
# ===============================================================


async def test_create_etiqueta_loga_com_id(client, session, token):
    """Create de etiqueta grava o log com o id gerado (exige o flush)."""
    response = await client.post(
        ETIQUETAS_URL,
        json={'nome': 'Nova Tag', 'cor': '#00FF00', 'descricao': 'desc'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.CREATED
    etiqueta_id = response.json()['data']['id']

    logs = await _logs(session, RESOURCE_ETIQUETA, action='create')
    assert len(logs) == 1
    assert logs[0].resource_id == etiqueta_id
    assert logs[0].before is None
    assert json.loads(logs[0].after) == {
        'nome': 'Nova Tag',
        'cor': '#00FF00',
        'descricao': 'desc',
    }
    # Nao polui o recurso da OM (a Etiqueta do CEGEP tem id proprio)
    assert await _logs(session, RESOURCE) == []


async def test_update_etiqueta_loga_diff(client, session, token):
    """Update de etiqueta grava before/after."""
    etq = Etiqueta(nome='Antiga', cor='#000000', descricao='d', uae='11gt')
    session.add(etq)
    await session.commit()
    await session.refresh(etq)

    response = await client.put(
        f'{ETIQUETAS_URL}{etq.id}',
        json={'nome': 'Nova'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE_ETIQUETA, action='update')
    assert len(logs) == 1
    assert json.loads(logs[0].before)['nome'] == 'Antiga'
    assert json.loads(logs[0].after)['nome'] == 'Nova'


async def test_update_etiqueta_sem_mudanca_nao_loga(client, session, token):
    """Reenviar os mesmos valores da etiqueta nao gera log."""
    etq = Etiqueta(nome='Igual', cor='#000000', descricao='d', uae='11gt')
    session.add(etq)
    await session.commit()
    await session.refresh(etq)

    response = await client.put(
        f'{ETIQUETAS_URL}{etq.id}',
        json={'nome': 'Igual', 'cor': '#000000', 'descricao': 'd'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    assert await _logs(session, RESOURCE_ETIQUETA, action='update') == []


async def test_delete_etiqueta_loga_snapshot_anterior(
    client, session, token
):
    """Delete de etiqueta guarda o estado anterior e o id removido."""
    etq = Etiqueta(nome='Sai', cor='#123456', descricao='d', uae='11gt')
    session.add(etq)
    await session.commit()
    await session.refresh(etq)
    etiqueta_id = etq.id

    response = await client.delete(
        f'{ETIQUETAS_URL}{etiqueta_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    logs = await _logs(session, RESOURCE_ETIQUETA, action='delete')
    assert len(logs) == 1
    assert logs[0].resource_id == etiqueta_id
    assert logs[0].after is None
    assert json.loads(logs[0].before)['nome'] == 'Sai'
