"""
Testes para o endpoint POST /ops/trips/.

Este endpoint cria um novo tripulante.
"""

from http import HTTPStatus

import pytest

from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio


async def test_create_trip_success(client, session, token):
    """Testa criação de tripulante com sucesso."""
    # Cria um usuário que não tem tripulante
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'abc',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['status'] == 'success'
    assert 'message' in data
    assert 'data' in data
    assert data['data']['trig'] == 'abc'
    assert data['data']['active'] is True
    assert data['data']['func'] == 'pil'


async def test_create_trip_returns_correct_message(client, session, token):
    """Testa que a mensagem de sucesso está correta."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'xyz',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['status'] == 'success'
    assert data['message'] == 'Tripulante adicionado com sucesso'


async def test_create_trip_duplicate_trig_same_uae_fails(
    client, session, users, token
):
    """Testa que não permite trigrama duplicado na mesma UAE."""
    user, other_user = users

    # Cria um tripulante com trigrama 'dup'
    existing_trip = TripFactory(user_id=user.id, trig='dup', uae='11gt')
    session.add(existing_trip)
    await session.commit()

    # Tenta criar outro tripulante com mesmo trigrama na mesma UAE
    trip_data = {
        'user_id': other_user.id,
        'trig': 'dup',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data['status'] == 'error'
    assert data['message'] == 'Trigrama já registrado'


async def test_create_trip_duplicate_user_same_uae_fails(
    client, session, users, token
):
    """Testa que não permite mesmo usuário duplicado na mesma UAE."""
    user, _ = users

    # Cria um tripulante para o usuário
    existing_trip = TripFactory(user_id=user.id, trig='aaa', uae='11gt')
    session.add(existing_trip)
    await session.commit()

    # Tenta criar outro tripulante para o mesmo usuário na mesma UAE
    trip_data = {
        'user_id': user.id,
        'trig': 'bbb',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data['status'] == 'error'
    assert data['message'] == 'Tripulante já registrado'


async def test_create_trip_trig_too_short_fails(client, session, token):
    """Testa que trigrama com menos de 3 caracteres falha."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'ab',  # Menos de 3 caracteres
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_trip_trig_too_long_fails(client, session, token):
    """Testa que trigrama com mais de 3 caracteres falha."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'abcd',  # Mais de 3 caracteres
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_trip_missing_user_id_fails(client, token):
    """Testa que user_id é obrigatório."""
    trip_data = {
        'trig': 'abc',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_trip_missing_trig_fails(client, session, token):
    """Testa que trig é obrigatório."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_trip_missing_active_org_fails(
    client, session, token_sistema
):
    """Sem org ativa no token_sistema, criar tripulante responde 400.

    A UAE deixou de ser campo do body e passou a vir do active_org do
    token_sistema (a fixture `token_sistema` não define org ativa).
    """
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'abc',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_create_trip_with_active_false(client, session, token):
    """Testa criação de tripulante inativo."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'def',
        'active': False,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': '2020-01-15',
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['active'] is False


async def test_create_trip_operacional_sem_data_op_fails(
    client, session, token
):
    """Tripulante não-aluno (oper != 'al') exige data_op → 422."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'ghi',
        'active': True,
        'func': 'pil',
        'oper': 'op',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_trip_aluno_sem_data_op_allowed(client, session, token):
    """Aluno (oper == 'al') pode ser criado sem data_op."""
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip_data = {
        'user_id': user.id,
        'trig': 'jkl',
        'active': True,
        'func': 'pil',
        'oper': 'al',
        'proj': 'kc-390',
        'data_op': None,
    }

    response = await client.post(
        '/ops/trips/',
        headers={'Authorization': f'Bearer {token}'},
        json=trip_data,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_trip_without_authentication_fails(client):
    """Testa que o endpoint requer autenticação."""
    trip_data = {
        'user_id': 1,
        'trig': 'abc',
        'active': True,
    }

    response = await client.post('/ops/trips/', json=trip_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
