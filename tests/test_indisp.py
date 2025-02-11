from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_get_crew_indisp(client):
    response = await client.get(
        '/indisp/', params={'funcao': 'mc', 'uae': '11gt'}
    )

    assert response.status_code == HTTPStatus.OK
    # assert response.json() == postos
