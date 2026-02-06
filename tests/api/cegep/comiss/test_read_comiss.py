"""
Testes para os endpoints GET /cegep/comiss/.

Endpoints:
- GET /cegep/comiss/ - Lista comissionamentos com filtros
- GET /cegep/comiss/{comiss_id} - Detalhes com missoes

Requer autenticacao.
"""

from datetime import date, datetime, timedelta
from http import HTTPStatus

import pytest

from tests.factories import ComissFactory, FragMisFactory, UserFragFactory

pytestmark = pytest.mark.anyio


# ============================================================
# GET /cegep/comiss/ - Listar comissionamentos
# ============================================================


async def test_list_comiss_empty(client, token):
    """Testa listagem vazia."""
    response = await client.get(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_list_comiss_success(client, session, token, users):
    """Testa listagem de comissionamentos."""
    user, other_user = users

    # Cria comissionamentos
    comiss1 = ComissFactory(user_id=user.id)
    comiss2 = ComissFactory(user_id=other_user.id, status='fechado')
    session.add_all([comiss1, comiss2])
    await session.commit()

    response = await client.get(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 2


async def test_list_comiss_filter_by_user_id(client, session, token, users):
    """Testa filtro por user_id."""
    user, other_user = users

    comiss1 = ComissFactory(user_id=user.id)
    comiss2 = ComissFactory(user_id=other_user.id, status='fechado')
    session.add_all([comiss1, comiss2])
    await session.commit()

    response = await client.get(
        f'/cegep/comiss/?user_id={user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['user']['id'] == user.id


async def test_list_comiss_filter_by_status(client, session, token, users):
    """Testa filtro por status."""
    user, other_user = users

    comiss_aberto = ComissFactory(user_id=user.id, status='aberto')
    comiss_fechado = ComissFactory(user_id=other_user.id, status='fechado')
    session.add_all([comiss_aberto, comiss_fechado])
    await session.commit()

    # Filtra abertos
    response = await client.get(
        '/cegep/comiss/?status=aberto',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['status'] == 'aberto'


async def test_list_comiss_fechado_limit_20(client, session, token, users):
    """Testa que status='fechado' limita a 20 resultados."""
    user, other_user = users
    today = date.today()

    # Cria 25 comissionamentos fechados (mais que o limite de 20)
    comiss_list = []
    for i in range(25):
        comiss = ComissFactory(
            user_id=user.id if i % 2 == 0 else other_user.id,
            status='fechado',
            data_ab=today - timedelta(days=365 + i * 100),
            data_fc=today - timedelta(days=275 + i * 100),
        )
        comiss_list.append(comiss)

    session.add_all(comiss_list)
    await session.commit()

    # Filtra fechados - deve retornar no maximo 20
    response = await client.get(
        '/cegep/comiss/?status=fechado',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 20  # Limite de 20 para status fechado


async def test_list_comiss_filter_by_search(client, session, token, users):
    """Testa filtro por nome_guerra."""
    user, other_user = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()

    # Busca pelo nome_guerra do usuario
    response = await client.get(
        f'/cegep/comiss/?search={user.nome_guerra}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) >= 1
    assert resp['data'][0]['user']['nome_guerra'] == user.nome_guerra


async def test_list_comiss_includes_cache_values(
    client, session, token, users
):
    """Testa que listagem inclui valores do cache."""
    user, _ = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()

    response = await client.get(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data'][0]

    # Verifica campos de cache presentes
    assert 'dias_comp' in data
    assert 'diarias_comp' in data
    assert 'vals_comp' in data
    assert 'modulo' in data
    assert 'completude' in data
    assert 'missoes_count' in data


async def test_list_comiss_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/comiss/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# GET /cegep/comiss/{comiss_id} - Detalhes com missoes
# ============================================================


async def test_get_comiss_by_id_success(client, session, token, users):
    """Testa busca de comissionamento por ID."""
    user, _ = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    response = await client.get(
        f'/cegep/comiss/{comiss.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data']['id'] == comiss.id
    assert resp['data']['user']['id'] == user.id
    assert 'missoes' in resp['data']


async def test_get_comiss_by_id_not_found(client, token):
    """Testa busca de comissionamento inexistente."""
    response = await client.get(
        '/cegep/comiss/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert 'encontrado' in resp['message'].lower()


async def test_get_comiss_by_id_includes_missoes(
    client, session, token, users
):
    """Testa que detalhes incluem missoes vinculadas."""
    user, _ = users
    today = date.today()

    # Cria comissionamento
    comiss = ComissFactory(
        user_id=user.id,
        data_ab=today - timedelta(days=30),
        data_fc=today + timedelta(days=60),
    )
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    # Cria missao dentro do periodo do comissionamento
    afast = datetime.now() - timedelta(days=10)
    regres = datetime.now() - timedelta(days=7)

    missao = FragMisFactory(afast=afast, regres=regres)
    session.add(missao)
    await session.commit()
    await session.refresh(missao)

    # Vincula usuario a missao como comissionado
    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='c',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()

    response = await client.get(
        f'/cegep/comiss/{comiss.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert 'missoes' in resp['data']
    assert isinstance(resp['data']['missoes'], list)


async def test_get_comiss_by_id_without_token(client, session, users):
    """Testa que requisicao sem token falha."""
    user, _ = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    response = await client.get(f'/cegep/comiss/{comiss.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
