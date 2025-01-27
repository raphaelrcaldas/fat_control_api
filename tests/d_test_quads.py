from http import HTTPStatus

from fcontrol_api.schemas.quads import QuadPublic


def test_create_quad(client):
    response = client.post(
        'ops/quads/',
        json=[
            {
                'trip_id': 5,
                'description': 'testtest',
                'type': 'sobr-verm',
                'value': 1,
            }
        ],
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == [
        {
            'trip_id': 5,
            'id': 1,
            'description': 'testtest',
            'type': 'sobr-verm',
            'value': 1,
        }
    ]


def test_create_quad_error_ja_existe(client, quad):
    response = client.post(
        'ops/quads/',
        json=[
            {
                'trip_id': quad.trip_id,
                'description': 'check desc',
                'type': quad.type,
                'value': quad.value,
            }
        ],
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {'detail': 'Quadrinho já registrado'}


def test_list_quad_by_trip(client, quad):
    quad_schema = QuadPublic.model_validate(quad).model_dump()

    response = client.get(
        f'ops/quads/trip/{quad.trip_id}',
        params={
            'type': quad.type,
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == [quad_schema]


def test_delete_quad(client, quad):
    response = client.delete(
        f'ops/quads/{quad.id}',
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {'detail': 'Quadrinho deletado'}


def test_delete_quad_error_not_found(client, quad):
    response = client.delete(
        f'ops/quads/{quad.id + 1}',
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {'detail': 'Quad not found'}


def test_update_quad(client, quad):
    response = client.patch(
        f'ops/quads/{quad.id}',
        json={
            'value': 250606,
            'type': 'other type',
            'description': 'desc update',
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        'id': quad.id,
        'trip_id': quad.trip_id,
        'value': 250606,
        'type': 'other type',
        'description': 'desc update',
    }


def test_update_quad_error_not_found(client, quad):
    response = client.patch(
        f'ops/quads/{quad.id + 1}',
        json={
            'value': 250606,
            'type': 'other type',
            'description': 'desc update',
        },
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {'detail': 'Quad not found'}
