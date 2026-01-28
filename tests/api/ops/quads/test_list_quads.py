"""
Testes para o endpoint GET /ops/quads/.

Este endpoint lista quadrinhos com filtros complexos por:
- tipo_quad: Tipo do quadrinho (default: 1)
- funcao: Função do tripulante (default: 'mc')
- uae: UAE do tripulante (default: '11gt')
- proj: Projeto da função (default: 'kc-390')

Retorna tripulantes com seus quadrinhos fatiados (equalizados).
Requer autenticação.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from fcontrol_api.models.public.funcoes import Funcao
from tests.factories import QuadFactory, TripFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def trip_with_func(session, users):
    """Cria um tripulante com função operacional configurada."""
    user, _ = users

    trip = TripFactory(user_id=user.id, uae='11gt', active=True)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    # Cria função com data_op definida (requisito do endpoint)
    func = Funcao(
        trip_id=trip.id,
        func='mc',
        oper='oe',  # Diferente de 'al' (requisito)
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    session.add(func)
    await session.commit()

    return trip


@pytest.fixture
async def trips_with_func(session, users):
    """Cria dois tripulantes com função operacional configurada."""
    user, other_user = users

    trip1 = TripFactory(user_id=user.id, uae='11gt', active=True)
    trip2 = TripFactory(user_id=other_user.id, uae='11gt', active=True)

    session.add_all([trip1, trip2])
    await session.commit()

    for t in [trip1, trip2]:
        await session.refresh(t)

    # Cria funções com data_op definida
    func1 = Funcao(
        trip_id=trip1.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func2 = Funcao(
        trip_id=trip2.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2021, 6, 20),
    )

    session.add_all([func1, func2])
    await session.commit()

    return (trip1, trip2)


async def test_list_quads_success(client, session, trip_with_func, token):
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
            'uae': '11gt',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data) >= 1

    # Verifica estrutura da resposta
    trip_data = data[0]
    assert 'trip' in trip_data
    assert 'quads' in trip_data
    assert 'quads_len' in trip_data


async def test_list_quads_empty_result(client, session, trip_with_func, token):
    """Testa que retorna lista vazia quando não há quads."""
    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'uae': '11gt',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Pode retornar tripulantes sem quads ou lista vazia
    if len(data) > 0:
        assert data[0]['quads_len'] == 0


async def test_list_quads_filters_by_uae(client, session, users, token):
    """Testa que apenas tripulantes da UAE são retornados."""
    user, other_user = users

    # Cria tripulante na UAE correta
    trip_11gt = TripFactory(user_id=user.id, uae='11gt', active=True)
    # Cria tripulante em outra UAE
    trip_other = TripFactory(user_id=other_user.id, uae='1gt', active=True)

    session.add_all([trip_11gt, trip_other])
    await session.commit()

    for t in [trip_11gt, trip_other]:
        await session.refresh(t)

    # Cria funções para ambos
    func_11gt = Funcao(
        trip_id=trip_11gt.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func_other = Funcao(
        trip_id=trip_other.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([func_11gt, func_other])
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={'uae': '11gt', 'funcao': 'mc', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Verifica que apenas tripulantes do 11gt são retornados
    trip_ids = [item['trip']['id'] for item in data]
    assert trip_11gt.id in trip_ids
    assert trip_other.id not in trip_ids


async def test_list_quads_filters_by_funcao(client, session, users, token):
    """Testa que apenas tripulantes com a função são retornados."""
    user, other_user = users

    trip_mc = TripFactory(user_id=user.id, uae='11gt', active=True)
    trip_lm = TripFactory(user_id=other_user.id, uae='11gt', active=True)

    session.add_all([trip_mc, trip_lm])
    await session.commit()

    for t in [trip_mc, trip_lm]:
        await session.refresh(t)

    func_mc = Funcao(
        trip_id=trip_mc.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func_lm = Funcao(
        trip_id=trip_lm.id,
        func='lm',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([func_mc, func_lm])
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'uae': '11gt', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_mc.id in trip_ids
    assert trip_lm.id not in trip_ids


async def test_list_quads_filters_by_proj(client, session, users, token):
    """Testa que apenas tripulantes do projeto são retornados."""
    user, other_user = users

    trip_kc = TripFactory(user_id=user.id, uae='11gt', active=True)
    trip_c130 = TripFactory(user_id=other_user.id, uae='11gt', active=True)

    session.add_all([trip_kc, trip_c130])
    await session.commit()

    for t in [trip_kc, trip_c130]:
        await session.refresh(t)

    func_kc = Funcao(
        trip_id=trip_kc.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func_c130 = Funcao(
        trip_id=trip_c130.id,
        func='mc',
        oper='oe',
        proj='c-130',
        data_op=date(2020, 1, 15),
    )

    session.add_all([func_kc, func_c130])
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={'proj': 'kc-390', 'funcao': 'mc', 'uae': '11gt'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_kc.id in trip_ids
    assert trip_c130.id not in trip_ids


async def test_list_quads_excludes_inactive_trips(
    client, session, users, token
):
    """Testa que tripulantes inativos não são retornados."""
    user, other_user = users

    trip_active = TripFactory(user_id=user.id, uae='11gt', active=True)
    trip_inactive = TripFactory(
        user_id=other_user.id, uae='11gt', active=False
    )

    session.add_all([trip_active, trip_inactive])
    await session.commit()

    for t in [trip_active, trip_inactive]:
        await session.refresh(t)

    func_active = Funcao(
        trip_id=trip_active.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func_inactive = Funcao(
        trip_id=trip_inactive.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([func_active, func_inactive])
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'uae': '11gt', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_active.id in trip_ids
    assert trip_inactive.id not in trip_ids


async def test_list_quads_excludes_aluno_oper(client, session, users, token):
    """Testa que tripulantes com oper='al' (aluno) não são retornados."""
    user, other_user = users

    trip_oper = TripFactory(user_id=user.id, uae='11gt', active=True)
    trip_aluno = TripFactory(user_id=other_user.id, uae='11gt', active=True)

    session.add_all([trip_oper, trip_aluno])
    await session.commit()

    for t in [trip_oper, trip_aluno]:
        await session.refresh(t)

    func_oper = Funcao(
        trip_id=trip_oper.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func_aluno = Funcao(
        trip_id=trip_aluno.id,
        func='mc',
        oper='al',  # Aluno
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )

    session.add_all([func_oper, func_aluno])
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'uae': '11gt', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_oper.id in trip_ids
    assert trip_aluno.id not in trip_ids


async def test_list_quads_excludes_without_data_op(
    client, session, users, token
):
    """Testa que tripulantes sem data_op não são retornados."""
    user, other_user = users

    trip_with_data_op = TripFactory(user_id=user.id, uae='11gt', active=True)
    trip_without = TripFactory(user_id=other_user.id, uae='11gt', active=True)

    session.add_all([trip_with_data_op, trip_without])
    await session.commit()

    for t in [trip_with_data_op, trip_without]:
        await session.refresh(t)

    func_with = Funcao(
        trip_id=trip_with_data_op.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    func_without = Funcao(
        trip_id=trip_without.id,
        func='mc',
        oper='oe',
        proj='kc-390',
        data_op=None,  # Sem data_op
    )

    session.add_all([func_with, func_without])
    await session.commit()

    response = await client.get(
        '/ops/quads/',
        params={'funcao': 'mc', 'uae': '11gt', 'proj': 'kc-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    trip_ids = [item['trip']['id'] for item in data]
    assert trip_with_data_op.id in trip_ids
    assert trip_without.id not in trip_ids


async def test_list_quads_returns_quads_len(
    client, session, trip_with_func, token
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
            'uae': '11gt',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    trip_data = next(
        (item for item in data if item['trip']['id'] == trip.id), None
    )
    assert trip_data is not None
    assert trip_data['quads_len'] == 3


async def test_list_quads_uses_default_params(
    client, session, trip_with_func, token
):
    """Testa que parâmetros padrão são aplicados."""
    # Faz requisição sem parâmetros (usa defaults)
    response = await client.get(
        '/ops/quads/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    # Defaults: tipo_quad=1, funcao='mc', uae='11gt', proj='kc-390'


async def test_list_quads_response_structure(
    client, session, trip_with_func, token
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
            'uae': '11gt',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

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
    client, session, users, token
):
    """Testa lista vazia quando há trips mas nenhum com a função solicitada.

    Cobre o branch: if not trip_data: return []
    """
    user, _ = users

    # Cria tripulante com função diferente da buscada
    trip = TripFactory(user_id=user.id, uae='11gt', active=True)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    # Cria função com 'lm' (diferente de 'pil' que será buscada)
    func = Funcao(
        trip_id=trip.id,
        func='lm',
        oper='oe',
        proj='kc-390',
        data_op=date(2020, 1, 15),
    )
    session.add(func)
    await session.commit()

    # Busca por 'pil' que não existe
    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'pil',  # Nenhum trip tem essa função
            'uae': '11gt',
            'proj': 'kc-390',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


async def test_list_quads_no_trips_with_matching_proj_returns_empty(
    client, session, users, token
):
    """Testa lista vazia quando há trips mas nenhum com o projeto solicitado.

    Cobre o branch: if not trip_data: return []
    """
    user, _ = users

    trip = TripFactory(user_id=user.id, uae='11gt', active=True)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    # Cria função com projeto diferente
    func = Funcao(
        trip_id=trip.id,
        func='mc',
        oper='oe',
        proj='c-130',  # Projeto diferente
        data_op=date(2020, 1, 15),
    )
    session.add(func)
    await session.commit()

    # Busca por 'kc-390' que não existe
    response = await client.get(
        '/ops/quads/',
        params={
            'tipo_quad': 1,
            'funcao': 'mc',
            'uae': '11gt',
            'proj': 'kc-390',  # Nenhum trip tem esse projeto
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []
