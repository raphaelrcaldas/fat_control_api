"""
Testes para o endpoint GET /ops/om/ (listagem de ordens de missao).

Testa paginacao, filtros por status, datas, busca textual e etiquetas.
"""

from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus

import pytest

from fcontrol_api.models.public.om import Etiqueta
from tests.factories import OrdemEtapaFactory, OrdemMissaoFactory

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om/'


async def test_list_ordens_empty(client, session, token):
    """Listagem sem ordens retorna lista vazia."""
    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []
    assert resp['total'] == 0
    assert resp['page'] == 1


async def test_list_ordens_returns_items(
    client, session, users, token
):
    """Listagem retorna ordens existentes."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['total'] == 1
    assert len(resp['data']) == 1
    assert resp['data'][0]['id'] == ordem.id


async def test_list_ordens_excludes_deleted(
    client, session, users, token
):
    """Ordens deletadas (soft delete) nao aparecem na listagem."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 0
    assert resp['data'] == []


async def test_list_ordens_pagination(
    client, session, users, token
):
    """Paginacao retorna itens corretos por pagina."""
    user, _ = users

    for _ in range(5):
        session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'page': 1, 'per_page': 2},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 5
    assert len(resp['data']) == 2
    assert resp['page'] == 1
    assert resp['per_page'] == 2
    assert resp['pages'] == 3


async def test_list_ordens_pagination_last_page(
    client, session, users, token
):
    """Ultima pagina retorna itens restantes."""
    user, _ = users

    for _ in range(5):
        session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'page': 3, 'per_page': 2},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 5
    assert len(resp['data']) == 1
    assert resp['page'] == 3


async def test_list_ordens_filter_status(
    client, session, users, token
):
    """Filtro por status retorna apenas ordens com status especifico."""
    user, _ = users

    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='rascunho'
        )
    )
    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='aprovada'
        )
    )
    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='aprovada'
        )
    )
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'status': 'aprovada'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 2
    for item in resp['data']:
        assert item['status'] == 'aprovada'


async def test_list_ordens_filter_multiple_status(
    client, session, users, token
):
    """Filtro com multiplos status retorna ordens de ambos."""
    user, _ = users

    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='rascunho'
        )
    )
    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='aprovada'
        )
    )
    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='cancelada'
        )
    )
    await session.commit()

    response = await client.get(
        BASE_URL,
        params=[
            ('status', 'rascunho'),
            ('status', 'aprovada'),
        ],
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 2


async def test_list_ordens_filter_status_ne(
    client, session, users, token
):
    """Filtro status_ne exclui ordens com status especifico."""
    user, _ = users

    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='rascunho'
        )
    )
    session.add(
        OrdemMissaoFactory(
            created_by=user.id, status='aprovada'
        )
    )
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'status_ne': 'rascunho'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['status'] == 'aprovada'


async def test_list_ordens_filter_data_inicio_fim(
    client, session, users, token
):
    """Filtro por data_inicio e data_fim retorna ordens no intervalo."""
    user, _ = users

    today = date.today()
    ordem_hoje = OrdemMissaoFactory(
        created_by=user.id, data_saida=today
    )
    ordem_passado = OrdemMissaoFactory(
        created_by=user.id,
        data_saida=today - timedelta(days=30),
    )
    session.add_all([ordem_hoje, ordem_passado])
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={
            'data_inicio': (today - timedelta(days=1)).isoformat(),
            'data_fim': (today + timedelta(days=1)).isoformat(),
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1


async def test_list_ordens_busca_by_numero(
    client, session, users, token
):
    """Busca por numero da ordem retorna resultado correto."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id, numero='OM-UNICO-123'
    )
    session.add(ordem)
    session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'busca': 'UNICO'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['numero'] == 'OM-UNICO-123'


async def test_list_ordens_busca_by_tipo(
    client, session, users, token
):
    """Busca por tipo da ordem retorna resultado correto."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id, tipo='instrucao'
    )
    session.add(ordem)
    session.add(
        OrdemMissaoFactory(
            created_by=user.id, tipo='transporte'
        )
    )
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'busca': 'instrucao'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['tipo'] == 'instrucao'


async def test_list_ordens_busca_by_icao(
    client, session, users, token
):
    """Busca por codigo ICAO de etapa retorna a ordem."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(
        ordem_id=ordem.id, origem='SBGL', dest='SBBR'
    )
    session.add(etapa)
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'busca': 'SBGL'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] >= 1
    ids = [item['id'] for item in resp['data']]
    assert ordem.id in ids


async def test_list_ordens_filter_etiquetas(
    client, session, users, token
):
    """Filtro por etiquetas retorna ordens vinculadas."""
    user, _ = users

    etiqueta = Etiqueta(
        nome='Urgente', cor='#FF0000', descricao='Teste'
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)

    ordem_com = OrdemMissaoFactory(created_by=user.id)
    ordem_sem = OrdemMissaoFactory(created_by=user.id)
    session.add_all([ordem_com, ordem_sem])
    await session.commit()
    await session.refresh(ordem_com)
    await session.refresh(ordem_sem)

    ordem_com.etiquetas.append(etiqueta)
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'etiquetas_ids': etiqueta.id},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['id'] == ordem_com.id


async def test_list_ordens_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.get(BASE_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
