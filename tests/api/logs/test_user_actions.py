"""
Testes para o endpoint GET /logs/user-actions.

Este endpoint lista logs de acoes de usuarios com filtros.
Requer autenticacao.
"""

from datetime import date, datetime
from http import HTTPStatus

import pytest

from tests.factories import UserActionLogFactory

pytestmark = pytest.mark.anyio


async def test_list_user_actions_success(
    client, session, users, token, user_action_logs
):
    """Testa listagem de logs com sucesso."""
    response = await client.get(
        '/logs/user-actions',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert isinstance(data, list)
    assert len(data) >= 1

    # Verifica estrutura do retorno
    item = data[0]
    assert 'id' in item
    assert 'user' in item
    assert 'action' in item
    assert 'resource' in item
    assert 'timestamp' in item
    assert 'nome_guerra' in item['user']


async def test_list_user_actions_filter_by_user_id(
    client, users, token, user_action_logs
):
    """Testa filtro por user_id."""
    user, _ = users

    response = await client.get(
        f'/logs/user-actions?user_id={user.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Todos os logs devem ser do usuario filtrado
    for log in data:
        assert log['user']['id'] == user.id


async def test_list_user_actions_filter_by_resource(
    client, token, user_action_logs
):
    """Testa filtro por resource."""
    response = await client.get(
        '/logs/user-actions?resource=users',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Todos os logs devem ser do resource filtrado
    for log in data:
        assert log['resource'] == 'users'


async def test_list_user_actions_filter_by_action(
    client, token, user_action_logs
):
    """Testa filtro por action."""
    response = await client.get(
        '/logs/user-actions?action=create',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Todos os logs devem ser da action filtrada
    for log in data:
        assert log['action'] == 'create'


async def test_list_user_actions_filter_by_resource_id(
    client, token, user_action_logs
):
    """Testa filtro por resource_id."""
    response = await client.get(
        '/logs/user-actions?resource_id=100',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Todos os logs devem ser do resource_id filtrado
    for log in data:
        assert log['resource_id'] == 100


async def test_list_user_actions_filter_by_start_date(
    client, session, users, token
):
    """Testa filtro por data inicial (start)."""
    user, _ = users

    # Cria um log (timestamp sera o momento da criacao)
    log = UserActionLogFactory(
        user_id=user.id,
        action='test_start',
        resource='test',
        resource_id=999,
    )
    session.add(log)
    await session.commit()

    # Filtra por hoje (deve excluir logs de ontem se timestamp < hoje)
    today = date.today().isoformat()

    response = await client.get(
        f'/logs/user-actions?start={today}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que todos os logs retornados sao >= start
    for log in data:
        log_date = datetime.fromisoformat(
            log['timestamp'].replace('Z', '+00:00')
        ).date()
        assert log_date >= date.today()


async def test_list_user_actions_filter_by_end_date(
    client, session, users, token
):
    """Testa filtro por data final (end)."""
    user, _ = users

    # Cria um log
    log = UserActionLogFactory(
        user_id=user.id,
        action='test_end',
        resource='test',
        resource_id=998,
    )
    session.add(log)
    await session.commit()

    # Filtra por hoje
    today = date.today().isoformat()

    response = await client.get(
        f'/logs/user-actions?end={today}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que todos os logs retornados sao <= end
    for log in data:
        log_date = datetime.fromisoformat(
            log['timestamp'].replace('Z', '+00:00')
        ).date()
        assert log_date <= date.today()


async def test_list_user_actions_filter_by_date_range(
    client, session, users, token
):
    """Testa filtro por intervalo de datas (start e end)."""
    user, _ = users

    # Cria um log
    log = UserActionLogFactory(
        user_id=user.id,
        action='test_range',
        resource='test',
        resource_id=997,
    )
    session.add(log)
    await session.commit()

    today = date.today().isoformat()

    response = await client.get(
        f'/logs/user-actions?start={today}&end={today}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que todos os logs retornados estao no intervalo
    for log in data:
        log_date = datetime.fromisoformat(
            log['timestamp'].replace('Z', '+00:00')
        ).date()
        assert log_date == date.today()


async def test_list_user_actions_limit_25(client, session, users, token):
    """Testa que o limite de 25 resultados e respeitado."""
    user, _ = users

    # Cria 30 logs
    logs = [
        UserActionLogFactory(
            user_id=user.id,
            action='test_limit',
            resource='test',
            resource_id=i,
        )
        for i in range(30)
    ]
    session.add_all(logs)
    await session.commit()

    response = await client.get(
        '/logs/user-actions',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Deve retornar no maximo 25 logs
    assert len(data) <= 25


async def test_list_user_actions_ordered_by_timestamp_desc(
    client, token, user_action_logs
):
    """Testa que os logs sao ordenados por timestamp decrescente."""
    response = await client.get(
        '/logs/user-actions',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica ordenacao decrescente
    timestamps = [
        datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
        for log in data
    ]

    for i in range(len(timestamps) - 1):
        assert timestamps[i] >= timestamps[i + 1]


async def test_list_user_actions_combined_filters(
    client, users, token, user_action_logs
):
    """Testa multiplos filtros combinados."""
    user, _ = users

    response = await client.get(
        f'/logs/user-actions?user_id={user.id}&action=create',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Todos os logs devem atender ambos os filtros
    for log in data:
        assert log['user']['id'] == user.id
        assert log['action'] == 'create'


async def test_list_user_actions_no_results(client, token):
    """Testa filtro que nao retorna resultados."""
    response = await client.get(
        '/logs/user-actions?user_id=999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_list_user_actions_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/logs/user-actions')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
