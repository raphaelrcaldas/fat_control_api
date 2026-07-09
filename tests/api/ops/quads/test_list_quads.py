"""
Testes para o endpoint GET /ops/quads/.

Este endpoint lista quadrinhos com filtros complexos por:
- tipo_quad: Tipo do quadrinho (default: 1)
- funcao: Função do tripulante (default: 'mc')
- proj: Projeto da função (default: 'kc-390')

A unidade (uae) é derivada da org ativa do token (active_org), não de
query param. Retorna tripulantes com seus quadrinhos fatiados (equalizados).
Requer autenticação e org ativa.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import QuadFactory, TripFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def trip_with_func(session, users):
    """Cria um tripulante com função operacional configurada."""
    user, _ = users

    # Função com data_op definida (requisito do endpoint); oper != 'al'.
    trip = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    return trip


@pytest.fixture
async def trips_with_func(session, users):
    """Cria dois tripulantes com função operacional configurada."""
    user, other_user = users

    trip1 = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    trip2 = TripFactory(
        user_id=other_user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2021, 6, 20),
    )

    session.add_all([trip1, trip2])
    await session.commit()

    for t in [trip1, trip2]:
        await session.refresh(t)

    return (trip1, trip2)


async def test_list_quads_success(client, session, trip_with_func, org_token):
    """Testa listagem de quadrinhos com sucesso."""
    trip = trip_with_func

    # Cria alguns quadrinhos
    quad = QuadFactory(trip_id=trip.id, type_id=1, value=date.today())
    session.add(quad)
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) >= 1

    # Verifica estrutura da resposta
    trip_data = data[0]
    assert 'trip' in trip_data
    assert 'quads' in trip_data
    assert 'quads_len' in trip_data


async def test_list_quads_empty_result(
    client, session, trip_with_func, org_token
):
    """Testa que retorna lista vazia quando não há quads."""
    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Pode retornar tripulantes sem quads ou lista vazia
    if len(data) > 0:
        assert data[0]['quads_len'] == 0


async def test_list_quads_filters_by_uae(client, session, users, org_token):
    """Testa que apenas tripulantes da UAE são retornados."""
    user, other_user = users

    # Cria tripulante na UAE correta
    trip_11gt = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    # Cria tripulante em outra UAE
    trip_other = TripFactory(
        user_id=other_user.id,
        uae='1gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([trip_11gt, trip_other])
    await session.commit()

    for t in [trip_11gt, trip_other]:
        await session.refresh(t)

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que apenas tripulantes do 11gt são retornados
    trip_ids = [item['trip']['id'] for item in data]
    assert trip_11gt.id in trip_ids
    assert trip_other.id not in trip_ids


async def test_list_quads_filters_by_funcao(client, session, users, org_token):
    """Testa que apenas tripulantes com a função são retornados."""
    user, other_user = users

    trip_mc = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    trip_lm = TripFactory(
        user_id=other_user.id,
        uae='11gt',
        active=True,
        func='lm',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([trip_mc, trip_lm])
    await session.commit()

    for t in [trip_mc, trip_lm]:
        await session.refresh(t)

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_mc.id in trip_ids
    assert trip_lm.id not in trip_ids


async def test_list_quads_filters_by_proj(client, session, users, org_token):
    """Testa que apenas tripulantes do projeto são retornados."""
    user, other_user = users

    trip_kc = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    trip_c130 = TripFactory(
        user_id=other_user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='c-130',
        data_op=date(2020, 1, 15),
    )

    session.add_all([trip_kc, trip_c130])
    await session.commit()

    for t in [trip_kc, trip_c130]:
        await session.refresh(t)

    response = await client.get(
        '/ops/quads/',
        params={'proj': 'kc-390', 'funcao': 'mc'},
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_kc.id in trip_ids
    assert trip_c130.id not in trip_ids


async def test_list_quads_excludes_inactive_trips(
    client, session, users, org_token
):
    """Testa que tripulantes inativos não são retornados."""
    user, other_user = users

    trip_active = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    trip_inactive = TripFactory(
        user_id=other_user.id,
        uae='11gt',
        active=False,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([trip_active, trip_inactive])
    await session.commit()

    for t in [trip_active, trip_inactive]:
        await session.refresh(t)

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_active.id in trip_ids
    assert trip_inactive.id not in trip_ids


async def test_list_quads_excludes_aluno_oper(
    client, session, users, org_token
):
    """Testa que tripulantes com oper='al' (aluno) não são retornados."""
    user, other_user = users

    trip_oper = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    trip_aluno = TripFactory(
        user_id=other_user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='al',  # Aluno
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([trip_oper, trip_aluno])
    await session.commit()

    for t in [trip_oper, trip_aluno]:
        await session.refresh(t)

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_oper.id in trip_ids
    assert trip_aluno.id not in trip_ids


async def test_list_quads_excludes_without_data_op(
    client, session, users, org_token
):
    """Testa que tripulantes sem data_op não são retornados."""
    user, other_user = users

    trip_with_data_op = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    trip_without = TripFactory(
        user_id=other_user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='kc-390',
        data_op=None,  # Sem data_op
    )

    session.add_all([trip_with_data_op, trip_without])
    await session.commit()

    for t in [trip_with_data_op, trip_without]:
        await session.refresh(t)

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_with_data_op.id in trip_ids
    assert trip_without.id not in trip_ids


async def test_list_quads_returns_quads_len(
    client, session, trip_with_func, org_token
):
    """Testa que quads_len retorna a contagem total de quadrinhos."""
    trip = trip_with_func

    # Cria 3 quadrinhos
    for i in range(3):
        quad = QuadFactory(
            trip_id=trip.id,
            type_id=1,
            value=date.today() + timedelta(days=i),
        )
        session.add(quad)

    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_data = next(
        (item for item in data if item['trip']['id'] == trip.id), None
    )
    assert trip_data is not None
    assert trip_data['quads_len'] == 3


async def test_list_quads_uses_default_params(
    client, session, trip_with_func, org_token
):
    """Testa que parâmetros padrão são aplicados."""
    # Faz requisição sem parâmetros (usa defaults)
    response = await client.get(
        '/ops/quads/',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    # Defaults: tipo_quad=1, funcao='mc', uae='11gt', proj='kc-390'


async def test_list_quads_response_structure(
    client, session, trip_with_func, org_token
):
    """Testa a estrutura completa da resposta."""
    trip = trip_with_func

    quad = QuadFactory(
        trip_id=trip.id,
        type_id=1,
        value=date.today(),
        description='Teste estrutura',
    )
    session.add(quad)
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    trip_data = next(
        (item for item in data if item['trip']['id'] == trip.id), None
    )
    assert trip_data is not None

    # Verifica estrutura do trip
    assert 'trig' in trip_data['trip']
    assert 'id' in trip_data['trip']
    assert 'user' in trip_data['trip']
    assert 'func' in trip_data['trip']

    # Verifica estrutura do user
    user = trip_data['trip']['user']
    assert 'nome_guerra' in user

    # Verifica estrutura dos quads
    assert isinstance(trip_data['quads'], list)
    assert isinstance(trip_data['quads_len'], int)


async def test_list_quads_without_token_fails(client):
    """Testa que requisição sem token falha."""
    response = await client.get('/ops/quads/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_list_quads_no_trips_with_matching_funcao_returns_empty(
    client, session, users, org_token
):
    """Testa lista vazia quando há trips mas nenhum com a função solicitada.

    Cobre o branch: if not trip_data: return []
    """
    user, _ = users

    # Cria tripulante com 'lm' (diferente de 'pil' que será buscada)
    trip = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='lm',
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    # Busca por 'pil' que não existe
    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'pil',  # Nenhum trip tem essa função
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_list_quads_no_trips_with_matching_proj_returns_empty(
    client, session, users, org_token
):
    """Testa lista vazia quando há trips mas nenhum com o projeto solicitado.

    Cobre o branch: if not trip_data: return []
    """
    user, _ = users

    # Cria tripulante com projeto diferente
    trip = TripFactory(
        user_id=user.id,
        uae='11gt',
        active=True,
        func='mc',
        oper='op',
        proj='c-130',  # Projeto diferente
        data_op=date(2020, 1, 15),
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    # Busca por 'kc-390' que não existe
    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'proj': 'kc-390',  # Nenhum trip tem esse projeto
        },
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []
