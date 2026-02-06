"""
Testes para o endpoint GET /indisp/user/{id}.

Este endpoint lista indisponibilidades de um usuário específico.
Requer autenticação (middleware global).
Suporta filtros opcionais: date_from, date_to, mtv.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import IndispFactory

pytestmark = pytest.mark.anyio


async def test_get_indisp_user_success(client, users, indisp, token):
    """Testa listagem de indisponibilidades de um usuário."""
    _, other_user = users

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['id'] == indisp.id


async def test_get_indisp_user_no_indisps_returns_empty(client, users, token):
    """Testa que usuário sem indisps retorna lista vazia."""
    _, other_user = users

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_get_indisp_user_ordered_by_date_end_desc(
    client, session, users, token
):
    """Testa que indisps são ordenadas por date_end desc (mais recente)."""
    user, other_user = users

    # Cria indisps com datas diferentes
    old_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=30),
        date_end=date.today() - timedelta(days=25),
        mtv='fer',
    )
    new_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='svc',
    )

    session.add_all([old_indisp, new_indisp])
    await session.commit()

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 2
    # Mais recente primeiro
    assert data[0]['id'] == new_indisp.id
    assert data[1]['id'] == old_indisp.id


async def test_get_indisp_user_filter_date_from(client, session, users, token):
    """Testa filtro date_from (indisps com date_end >= date_from)."""
    user, other_user = users

    old_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=30),
        date_end=date.today() - timedelta(days=25),
        mtv='fer',
    )
    new_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='svc',
    )

    session.add_all([old_indisp, new_indisp])
    await session.commit()

    # Filtra apenas indisps com date_end >= 10 dias atrás
    date_from = (date.today() - timedelta(days=10)).isoformat()
    response = await client.get(
        f'/indisp/user/{other_user.id}',
        params={'date_from': date_from},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['id'] == new_indisp.id


async def test_get_indisp_user_filter_date_to(client, session, users, token):
    """Testa filtro date_to (indisps com date_start <= date_to)."""
    user, other_user = users

    old_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=30),
        date_end=date.today() - timedelta(days=25),
        mtv='fer',
    )
    future_indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() + timedelta(days=30),
        date_end=date.today() + timedelta(days=35),
        mtv='svc',
    )

    session.add_all([old_indisp, future_indisp])
    await session.commit()

    # Filtra apenas indisps com date_start <= hoje
    date_to = date.today().isoformat()
    response = await client.get(
        f'/indisp/user/{other_user.id}',
        params={'date_to': date_to},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['id'] == old_indisp.id


async def test_get_indisp_user_filter_date_range(
    client, session, users, token
):
    """Testa filtro combinado date_from e date_to."""
    user, other_user = users

    very_old = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=60),
        date_end=date.today() - timedelta(days=55),
        mtv='fer',
    )
    in_range = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=10),
        date_end=date.today() + timedelta(days=5),
        mtv='svc',
    )
    future = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() + timedelta(days=30),
        date_end=date.today() + timedelta(days=35),
        mtv='lic',
    )

    session.add_all([very_old, in_range, future])
    await session.commit()

    date_from = (date.today() - timedelta(days=20)).isoformat()
    date_to = (date.today() + timedelta(days=10)).isoformat()

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        params={'date_from': date_from, 'date_to': date_to},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['id'] == in_range.id


async def test_get_indisp_user_filter_mtv(client, session, users, token):
    """Testa filtro por mtv (motivo da indisponibilidade)."""
    user, other_user = users

    ferias = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    servico = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=3),
        mtv='svc',
    )

    session.add_all([ferias, servico])
    await session.commit()

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        params={'mtv': 'fer'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['id'] == ferias.id
    assert data[0]['mtv'] == 'fer'


async def test_get_indisp_user_combined_filters(client, session, users, token):
    """Testa filtros combinados: date_from + date_to + mtv."""
    user, other_user = users

    # Dentro do range, mtv correto
    match = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=5),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    # Dentro do range, mtv errado
    wrong_mtv = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=5),
        date_end=date.today() + timedelta(days=5),
        mtv='svc',
    )
    # Fora do range, mtv correto
    wrong_date = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=60),
        date_end=date.today() - timedelta(days=55),
        mtv='fer',
    )

    session.add_all([match, wrong_mtv, wrong_date])
    await session.commit()

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        params={
            'date_from': (date.today() - timedelta(days=10)).isoformat(),
            'date_to': (date.today() + timedelta(days=10)).isoformat(),
            'mtv': 'fer',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['id'] == match.id


async def test_get_indisp_user_includes_response_fields(
    client, session, users, token
):
    """Testa que resposta inclui campos do IndispOut."""
    user, other_user = users

    indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
        obs='Teste campos',
    )

    session.add(indisp)
    await session.commit()
    await session.refresh(indisp)

    response = await client.get(
        f'/indisp/user/{other_user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1

    item = data[0]
    assert 'id' in item
    assert 'user_id' in item
    assert 'date_start' in item
    assert 'date_end' in item
    assert 'mtv' in item
    assert 'obs' in item
    assert 'created_at' in item


async def test_get_indisp_user_invalid_user_returns_empty(client, token):
    """Testa que user_id não existente retorna lista vazia."""
    response = await client.get(
        '/indisp/user/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_get_indisp_user_without_token_fails(client, users):
    """Testa que requisição sem token falha."""
    _, other_user = users

    response = await client.get(f'/indisp/user/{other_user.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
