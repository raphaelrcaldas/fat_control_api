from http import HTTPStatus

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.anyio


async def test_get_token(client, users):
    user, _ = users

    response = await client.post(
        '/auth/token',
        data={'username': user.saram, 'password': user.clean_password},
    )

    token = response.json()

    assert response.status_code == HTTPStatus.OK
    assert 'access_token' in token
    assert 'token_type' in token


async def test_token_expired_after_time(client, users):
    user, _ = users

    with freeze_time('2023-07-14 12:00:00'):
        response = await client.post(
            '/auth/token',
            data={'username': user.saram, 'password': user.clean_password},
        )
        assert response.status_code == HTTPStatus.OK
        token = response.json()['access_token']

    with freeze_time('2023-07-14 12:31:00'):
        response = await client.post(
            '/indisp/',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'user_id': 1,
                'date_start': '2023-03-23',
                'date_end': '2023-03-24',
                'mtv': 'teste_teste',
                'obs': 'obs_obs',
            },
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json() == {'detail': 'Could not validate credentials'}


async def test_token_inexistent_user(client):
    response = await client.post(
        '/auth/token',
        data={'username': 555555, 'password': 'testtest'},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Dados inválidos'}


async def test_token_wrong_password(client, users):
    user, _ = users

    response = await client.post(
        '/auth/token',
        data={'username': user.saram, 'password': 'wrong_password'},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Dados inválidos'}


async def test_refresh_token(client, users):
    user, _ = users

    response = await client.post(
        '/auth/token',
        data={'username': user.saram, 'password': user.clean_password},
    )

    token = response.json()['access_token']

    response = await client.post(
        '/auth/refresh_token',
        headers={'Authorization': f'Bearer {token}'},
    )

    data = response.json()

    assert response.status_code == HTTPStatus.OK
    assert 'access_token' in data
    assert 'token_type' in data
    assert data['token_type'] == 'bearer'


async def test_token_expired_dont_refresh(client, users):
    user, _ = users

    with freeze_time('2023-07-14 12:00:00'):
        response = await client.post(
            '/auth/token',
            data={'username': user.saram, 'password': user.clean_password},
        )
        assert response.status_code == HTTPStatus.OK
        token = response.json()['access_token']

    with freeze_time('2023-07-14 12:31:00'):
        response = await client.post(
            '/auth/refresh_token',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json() == {'detail': 'Could not validate credentials'}
