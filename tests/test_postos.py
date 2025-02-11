from http import HTTPStatus

import pytest

from fcontrol_api.schemas.posto_grad import PostoGradSchema

pytestmark = pytest.mark.anyio


async def test_get_postos(client, posto_table):
    response = await client.get('/postos/')

    postos = list(
        map(
            lambda posto: PostoGradSchema.model_validate(posto).model_dump(
                mode='json'
            ),
            posto_table,
        )
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == postos
