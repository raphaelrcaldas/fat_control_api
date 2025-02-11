import base64
from http import HTTPStatus

import pytest
from jwt import decode

from fcontrol_api.security import create_access_token, settings

pytestmark = pytest.mark.anyio


async def test_jwt():
    data = {'test': 'test'}
    token = create_access_token(data)

    decoded = decode(
        token,
        base64.urlsafe_b64decode(settings.SECRET_KEY + '========'),
        algorithms=[settings.ALGORITHM],
    )

    assert decoded['test'] == data['test']
    assert decoded['exp']


async def test_current_user_no_user_id(client):
    data = {'test': 'test'}
    token = create_access_token(data)

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


async def test_current_user_decode_error(client):
    token = 'wrong_token'

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


async def test_current_user_no_user_in_db(client):
    data = {'user_id': 1}
    token = create_access_token(data)

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
