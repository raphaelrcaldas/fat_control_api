import random
from http import HTTPStatus

import pytest

from fcontrol_api.schemas.users import UserPublic, UserSchema
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio


async def test_create_user(client, posto_table):
    user = UserFactory()
    user_schema = UserSchema.model_validate(user).model_dump(mode='json')

    response = await client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.CREATED

    data = response.json()
    assert data == {
        'detail': 'Usuário Adicionado com sucesso',
        'data': UserPublic.model_validate(data['data']).model_dump(),
    }


async def test_create_user_error_saram(client, users):
    (user, _) = users

    new_user = UserFactory(saram=user.saram)

    user_schema = UserSchema.model_validate(new_user).model_dump(mode='json')

    response = await client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'SARAM já registrado',
    }


async def test_create_user_error_id_fab(client, users):
    (user, _) = users

    new_user = UserFactory(id_fab=user.id_fab)
    user_schema = UserSchema.model_validate(new_user).model_dump(mode='json')

    response = await client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'ID FAB já registrado',
    }


async def test_create_user_error_cpf(client, users):
    (user, _) = users

    new_user = UserFactory(cpf=user.cpf)
    user_schema = UserSchema.model_validate(new_user).model_dump(mode='json')

    response = await client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'CPF já registrado',
    }


async def test_create_user_error_zimbra(client, users):
    (user, _) = users

    new_user = UserFactory(email_fab=user.email_fab)
    user_schema = UserSchema.model_validate(new_user).model_dump(mode='json')

    response = await client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'Zimbra já registrado',
    }


async def test_create_user_error_email_pess(client, users):
    (user, _) = users

    new_user = UserFactory(email_pess=user.email_pess)
    user_schema = UserSchema.model_validate(new_user).model_dump(mode='json')

    response = await client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'Email pessoal já registrado',
    }


async def test_read_users(client):
    response = await client.get('/users/')

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


async def test_read_users_with_users(client, users):
    users_list = [
        UserPublic.model_validate(user).model_dump() for user in users
    ]

    response = await client.get('/users/')

    assert response.json() == users_list


async def test_get_user(client, users):
    (user, _) = users

    user_schema = UserSchema.model_validate(user).model_dump(mode='json')

    response = await client.get(f'/users/{user.id}')

    assert response.status_code == HTTPStatus.OK
    assert response.json() == user_schema


async def test_get_error_no_user(client):
    response = await client.get('/users/1')

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {
        'detail': 'User not found',
    }


async def test_update_user(client, users):
    (user, _) = users

    user.nome_guerra = 'test_update'

    user_schema = UserSchema.model_validate(user).model_dump(mode='json')

    response = await client.put(
        f'/users/{user.id}',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        'detail': 'Usuário atualizado com sucesso',
        'data': UserPublic.model_validate(
            response.json()['data']
        ).model_dump(),
    }


async def test_update_user_error_no_user(client, users):
    def random_id(numeros_excluir):
        numeros_possiveis = list(range(1, 999))
        for numero in numeros_excluir:
            if numero in numeros_possiveis:
                numeros_possiveis.remove(numero)
        return random.choice(numeros_possiveis)

    (user, _) = users

    user_schema = UserSchema.model_validate(user).model_dump(mode='json')

    response = await client.put(
        f'/users/{random_id([i.id for i in users])}',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {
        'detail': 'User not found',
    }


# def test_delete_user(client, user):
#     response = client.delete(
#         f'/users/{user.id}',
#     )

#     assert response.status_code == HTTPStatus.OK
#     assert response.json() == {'message': 'User deleted'}
