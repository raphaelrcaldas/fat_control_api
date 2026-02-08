"""
Testes para o endpoint PUT /ops/om/{id} (atualizacao de ordem).

Testa atualizacao de campos, transicao de status, geracao de numero
sequencial e substituicao de etapas.
"""

from datetime import date, datetime, timezone
from http import HTTPStatus

import pytest

from fcontrol_api.models.public.om import Etiqueta
from tests.factories import OrdemMissaoFactory

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om'


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
    """Helper para criar payload de etapa."""
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


async def test_update_ordem_simple_fields(
    client, session, users, token
):
    """Atualizacao de campos simples funciona."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        tipo='instrucao',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'tipo': 'transporte', 'projeto': 'KC-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['tipo'] == 'transporte'
    assert data['projeto'] == 'KC-390'


async def test_update_ordem_not_found(
    client, session, token
):
    """Atualizacao de ordem inexistente retorna 404."""
    response = await client.put(
        f'{BASE_URL}/99999',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_ordem_deleted_returns_404(
    client, session, users, token
):
    """Atualizacao de ordem deletada retorna 404."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_rascunho_to_aprovada_generates_numero(
    client, session, users, token
):
    """Transicao rascunho -> aprovada gera numero sequencial."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='1/1 GT',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa_payload = _make_etapa()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={
            'status': 'aprovada',
            'etapas': [etapa_payload],
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['status'] == 'aprovada'
    assert data['numero'] == '001'


async def test_update_aprovada_sequential_numero(
    client, session, users, token
):
    """Segundo aprovacao no mesmo ano/UAE gera numero 002."""
    user, _ = users

    existing = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='001',
        uae='1/1 GT',
        data_saida=date(2025, 6, 15),
    )
    session.add(existing)
    await session.commit()

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='1/1 GT',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa_payload = _make_etapa()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={
            'status': 'aprovada',
            'etapas': [etapa_payload],
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['numero'] == '002'


async def test_update_aprovada_requires_etapa(
    client, session, users, token
):
    """Transicao para aprovada sem etapas falha (400)."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='1/1 GT',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'status': 'aprovada'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_replaces_etapas(
    client, session, users, token
):
    """Atualizacao de etapas substitui todas as existentes."""
    old_etapa = _make_etapa(
        origem='SBRF', dest='SBSV',
    )
    create_payload = {
        'matricula_anv': 2850,
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'uae': '1/1 GT',
        'esf_aer': 2,
        'campos_especiais': [],
        'etapas': [old_etapa],
        'tripulacao': None,
        'etiquetas_ids': [],
    }
    create_resp = await client.post(
        f'{BASE_URL}/',
        json=create_payload,
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    new_etapa = _make_etapa(origem='SBGL', dest='SBBR')

    response = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'etapas': [new_etapa]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verificar via GET separado (evita cache da sessao)
    get_resp = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert get_resp.status_code == HTTPStatus.OK
    data = get_resp.json()['data']
    assert len(data['etapas']) == 1
    assert data['etapas'][0]['origem'] == 'SBGL'
    assert data['etapas'][0]['dest'] == 'SBBR'


async def test_update_etapas_updates_data_saida(
    client, session, users, token
):
    """Atualizacao de etapas recalcula data_saida."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        data_saida=date(2025, 1, 1),
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    new_etapa = _make_etapa(
        dt_dep='2025-07-20T10:00:00',
        dt_arr='2025-07-20T11:30:00',
    )

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'etapas': [new_etapa]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['data_saida'] == '2025-07-20'


async def test_update_etiquetas(
    client, session, users, token
):
    """Atualizacao de etiquetas substitui as existentes."""
    user, _ = users

    etq1 = Etiqueta(nome='A', cor='#FF0000')
    etq2 = Etiqueta(nome='B', cor='#00FF00')
    session.add_all([etq1, etq2])
    await session.commit()
    await session.refresh(etq1)
    await session.refresh(etq2)

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.etiquetas.append(etq1)
    await session.commit()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'etiquetas_ids': [etq2.id]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert len(data['etiquetas']) == 1
    assert data['etiquetas'][0]['id'] == etq2.id


async def test_update_manual_numero_only_approved(
    client, session, users, token
):
    """Edicao manual de numero so permitida em ordens aprovadas."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'numero': '999'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_manual_numero_approved_success(
    client, session, users, token
):
    """Edicao manual de numero funciona para ordens aprovadas."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='001',
        uae='1/1 GT',
        data_saida=date(2025, 6, 15),
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'numero': '050'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['numero'] == '050'


async def test_update_manual_numero_duplicate_fails(
    client, session, users, token
):
    """Edicao manual com numero duplicado no mesmo ano/UAE falha."""
    user, _ = users

    existing = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='050',
        uae='1/1 GT',
        data_saida=date(2025, 6, 15),
    )
    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='001',
        uae='1/1 GT',
        data_saida=date(2025, 6, 15),
    )
    session.add_all([existing, ordem])
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'numero': '050'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_ordem_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.put(
        f'{BASE_URL}/1', json={'tipo': 'transporte'}
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
