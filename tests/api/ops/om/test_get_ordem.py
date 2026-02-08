"""
Testes para o endpoint GET /ops/om/{id} (detalhes de ordem de missao).

Testa busca por ID, retorno de relacionamentos e cenarios de erro.
"""

from datetime import datetime, timezone
from http import HTTPStatus

import pytest

from fcontrol_api.models.public.om import Etiqueta
from tests.factories import OrdemMissaoFactory

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om'


async def test_get_ordem_success(
    client, session, users, token
):
    """Busca por ID retorna ordem com todos os campos."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.get(
        f'{BASE_URL}/{ordem.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['id'] == ordem.id
    assert data['numero'] == ordem.numero
    assert data['matricula_anv'] == ordem.matricula_anv
    assert data['tipo'] == ordem.tipo
    assert data['status'] == ordem.status


async def test_get_ordem_includes_etapas(
    client, session, users, token
):
    """Resposta inclui etapas da ordem (via POST)."""
    etapa_payload = {
        'dt_dep': '2025-06-15T10:00:00',
        'origem': 'SBGL',
        'dest': 'SBBR',
        'dt_arr': '2025-06-15T11:30:00',
        'alternativa': 'SBCF',
        'tvoo_alt': 30,
        'qtd_comb': 15,
        'esf_aer': 'normal',
    }
    payload = {
        'matricula_anv': 2850,
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'uae': '1/1 GT',
        'esf_aer': 2,
        'campos_especiais': [],
        'etapas': [etapa_payload],
        'tripulacao': None,
        'etiquetas_ids': [],
    }

    create_resp = await client.post(
        f'{BASE_URL}/',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    response = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert len(data['etapas']) == 1
    assert data['etapas'][0]['origem'] == 'SBGL'
    assert data['etapas'][0]['dest'] == 'SBBR'


async def test_get_ordem_includes_etiquetas(
    client, session, users, token
):
    """Resposta inclui etiquetas da ordem (via POST)."""
    etiqueta = Etiqueta(
        nome='Tag', cor='#00FF00', descricao='desc'
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)

    payload = {
        'matricula_anv': 2850,
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'uae': '1/1 GT',
        'esf_aer': 2,
        'campos_especiais': [],
        'etapas': [],
        'tripulacao': None,
        'etiquetas_ids': [etiqueta.id],
    }

    create_resp = await client.post(
        f'{BASE_URL}/',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    response = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert len(data['etiquetas']) == 1
    assert data['etiquetas'][0]['nome'] == 'Tag'


async def test_get_ordem_not_found(client, session, token):
    """ID inexistente retorna 404."""
    response = await client.get(
        f'{BASE_URL}/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_get_ordem_deleted_returns_404(
    client, session, users, token
):
    """Ordem com soft delete retorna 404."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    response = await client.get(
        f'{BASE_URL}/{ordem.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_get_ordem_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.get(f'{BASE_URL}/1')
    assert response.status_code == HTTPStatus.UNAUTHORIZED
