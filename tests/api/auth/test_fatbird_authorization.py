"""
Testes específicos para autorização do cliente FATBIRD.

O cliente FATBIRD requer que o usuário seja um tripulante ativo,
conforme validação em validate_user_client_access.
"""

from http import HTTPStatus

import pytest

from tests.api.conftest import generate_pkce_pair
from tests.factories import TripFactory

pytestmark = pytest.mark.anyio


async def test_authorize_fatbird_with_active_tripulante_success(
    client, users, oauth_client, session
):
    """
    Testa autorização bem-sucedida no FATBIRD com tripulante ativo.

    Este teste cobre a validação do FATBIRD em validate_user_client_access
    quando o usuário é um tripulante ativo.
    """
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Cria um tripulante ativo associado ao usuário
    tripulante = TripFactory(user_id=user.id, active=True)
    session.add(tripulante)
    await session.commit()

    # Configura o cliente como FATBIRD
    oauth_client.client_id = 'fatbird'
    await session.commit()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': 'fatbird',
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert 'code' in data
    assert isinstance(data['code'], str)
    assert len(data['code']) > 0


async def test_authorize_fatbird_without_tripulante_fails(
    client, users, oauth_client, session
):
    """
    Testa falha na autorização do FATBIRD quando usuário não é tripulante.

    Cobre a linha 84-90 de fcontrol_api/services/auth.py onde
    valida se o usuário é um tripulante ativo no FATBIRD.
    """
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Configura o cliente como FATBIRD, mas NÃO cria tripulante para o usuário
    oauth_client.client_id = 'fatbird'
    await session.commit()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': 'fatbird',
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    resp = response.json()
    assert resp['status'] == 'error'
    assert (
        'apenas tripulantes ativos podem acessar o fatbird'
        in resp['message'].lower()
    )


async def test_authorize_fatbird_with_inactive_tripulante_fails(
    client, users, oauth_client, session
):
    """
    Testa falha na autorização do FATBIRD quando tripulante está inativo.

    Este teste garante que a validação verifica não apenas a existência
    do tripulante, mas também se ele está ativo.
    """
    user, _ = users
    code_verifier, code_challenge = generate_pkce_pair()

    # Cria um tripulante INATIVO associado ao usuário
    tripulante = TripFactory(user_id=user.id, active=False)
    session.add(tripulante)
    await session.commit()

    # Configura o cliente como FATBIRD
    oauth_client.client_id = 'fatbird'
    await session.commit()

    response = await client.post(
        '/auth/authorize',
        data={
            'client_id': 'fatbird',
            'redirect_uri': oauth_client.redirect_uri,
            'response_type': 'code',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'saram': user.saram,
            'password': user.clean_password,
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    resp = response.json()
    assert resp['status'] == 'error'
    assert (
        'apenas tripulantes ativos podem acessar o fatbird'
        in resp['message'].lower()
    )
