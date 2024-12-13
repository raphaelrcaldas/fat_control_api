from datetime import date
from http import HTTPStatus

from fcontrol_api.schemas.users import UserPublic, UserSchema
from tests.factories import UserFactory


def test_create_user(client):
    user = UserFactory(ult_promo=None, nasc=None)
    user_schema = UserSchema.model_validate(user).model_dump()

    response = client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.CREATED

    data = response.json()
    assert data == {
        'detail': 'Usuário Adicionado com sucesso',
        'data': UserPublic.model_validate(data['data']).model_dump(),
    }


def test_create_user_error_saram(client, user):
    new_user = UserFactory(saram=user.saram)

    user_schema = UserSchema.model_validate(new_user).model_dump()
    user_schema['nasc'] = user_schema['nasc'].isoformat()
    user_schema['ult_promo'] = user_schema['ult_promo'].isoformat()

    response = client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        'detail': 'SARAM já registrado',
    }


def test_create_user_error_id_fab(client, user):
    new_user = UserFactory(id_fab=user.id_fab, ult_promo=None, nasc=None)
    user_schema = UserSchema.model_validate(new_user).model_dump()

    response = client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = response.json()
    assert data == {
        'detail': 'ID FAB já registrado',
    }


def test_create_user_error_cpf(client, user):
    new_user = UserFactory(cpf=user.cpf, ult_promo=None, nasc=None)
    user_schema = UserSchema.model_validate(new_user).model_dump()

    response = client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = response.json()
    assert data == {
        'detail': 'CPF já registrado',
    }


def test_create_user_error_zimbra(client, user):
    new_user = UserFactory(email_fab=user.email_fab, ult_promo=None, nasc=None)
    user_schema = UserSchema.model_validate(new_user).model_dump()

    response = client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = response.json()
    assert data == {
        'detail': 'Zimbra já registrado',
    }


def test_create_user_error_email_pess(client, user):
    new_user = UserFactory(
        email_pess=user.email_pess, ult_promo=None, nasc=None
    )
    user_schema = UserSchema.model_validate(new_user).model_dump()

    response = client.post(
        '/users/',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST

    data = response.json()
    assert data == {
        'detail': 'Email pessoal já registrado',
    }


def test_read_users(client):
    response = client.get('/users')
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


def test_read_users_with_users(client, user):
    user_schema = UserPublic.model_validate(user).model_dump()
    response = client.get('/users/')
    assert response.json() == [user_schema]


def test_get_user(client, user):
    user_schema = UserSchema.model_validate(user).model_dump()

    response = client.get(f'/users/{user.id}')

    assert response.status_code == HTTPStatus.OK

    data = response.json()
    data['ult_promo'] = date.fromisoformat(data['ult_promo'])
    data['nasc'] = date.fromisoformat(data['nasc'])
    assert data == user_schema


def test_get_error_no_user(client):
    response = client.get('/users/1')

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {
        'detail': 'User not found',
    }


def test_update_user(client, user):
    user.nome_guerra = 'test_update'
    user.nasc = None
    user.ult_promo = None

    user_schema = UserSchema.model_validate(user).model_dump()

    response = client.put(
        f'/users/{user.id}',
        json=user_schema,
    )

    assert response.status_code == HTTPStatus.OK

    data = response.json()
    assert data == {
        'detail': 'Usuário atualizado com sucesso',
        'data': UserPublic.model_validate(data['data']).model_dump(),
    }


def test_update_user_error_no_user(client, user):
    user.nasc = None
    user.ult_promo = None
    user_schema = UserSchema.model_validate(user).model_dump()

    response = client.put(
        f'/users/{user.id + 1}',
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
