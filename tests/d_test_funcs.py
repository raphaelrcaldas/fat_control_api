from http import HTTPStatus


async def test_create_func(client, trip):
    r = await client.post(
        'ops/funcoes/',
        json={
            'trip_id': trip.id,
            'func': 'mc',
            'oper': 'al',
            'proj': 'kc-390',
            'data_op': None,
        },
    )

    assert r.status_code == HTTPStatus.CREATED
    assert r.json() == {
        'detail': 'Função cadastrada com sucesso',
        'data': {'trip_id': trip.id},
    }


def test_create_func_error_not_found(client):
    r = client.post(
        'ops/funcoes/',
        json={
            'trip_id': 1,
            'func': 'mc',
            'oper': 'al',
            'proj': 'kc-390',
            'data_op': None,
        },
    )

    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert r.json() == {
        'detail': 'Crew member not found',
    }


def test_create_func_error_func_ja_registrada(client, funcao):
    r = client.post(
        'ops/funcoes/',
        json={
            'trip_id': funcao.trip_id,
            'func': funcao.func,
            'oper': 'op',
            'proj': 'kc-390',
            'data_op': None,
        },
    )

    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert r.json() == {
        'detail': 'Função já registrada para esse tripulante',
    }


def test_update_func(client, funcao):
    r = client.put(
        f'ops/funcoes/{funcao.id}',
        json={
            'oper': 'al',
            'data_op': None,
        },
    )

    assert r.status_code == HTTPStatus.OK
    assert r.json() == {
        'detail': 'Função atualizada com sucesso',
        'data': {
            'id': 1,
            'trip_id': funcao.trip_id,
            'func': funcao.func,
            'proj': funcao.proj,
            'oper': 'al',
            'data_op': None,
        },
    }


def test_update_func_error_not_found(client, funcao):
    r = client.put(
        f'ops/funcoes/{funcao.id + 1}',
        json={
            'oper': 'al',
            'data_op': None,
        },
    )

    assert r.status_code == HTTPStatus.NOT_FOUND
    assert r.json() == {
        'detail': 'Crew func not found',
    }


def test_delete_func(client, funcao):
    r = client.delete(f'ops/funcoes/{funcao.id}')

    assert r.status_code == HTTPStatus.OK
    assert r.json() == {
        'detail': 'Função deletada',
    }


def test_delete_func_error_not_found(client, funcao):
    r = client.delete(f'ops/funcoes/{funcao.id + 1}')

    assert r.status_code == HTTPStatus.NOT_FOUND
    assert r.json() == {
        'detail': 'Crew function not found',
    }
