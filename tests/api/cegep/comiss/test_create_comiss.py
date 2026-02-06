"""
Testes para o endpoint POST /cegep/comiss/.

Este endpoint cria um novo comissionamento.
Requer autenticacao.

Regras de negocio:
- Apenas 1 comissionamento aberto por usuario
- Nao pode haver conflito de datas com outros comissionamentos
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from tests.factories import ComissFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def comiss_data(users):
    """Dados base para criar um comissionamento."""
    user, _ = users
    today = date.today()
    return {
        'user_id': user.id,
        'status': 'aberto',
        'dep': False,
        'data_ab': today.isoformat(),
        'qtd_aj_ab': 30.0,
        'valor_aj_ab': 5000.00,
        'data_fc': (today + timedelta(days=90)).isoformat(),
        'qtd_aj_fc': 30.0,
        'valor_aj_fc': 5000.00,
        'dias_cumprir': 60,
        'doc_prop': 'PROP-0001/2025',
        'doc_aut': 'AUT-0001/2025',
        'doc_enc': None,
    }


async def test_create_comiss_success(client, session, token, comiss_data):
    """Testa criacao de comissionamento com sucesso."""
    response = await client.post(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
        json=comiss_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'criado com sucesso' in resp['message'].lower()

    # Verifica no banco
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            Comissionamento.user_id == comiss_data['user_id']
        )
    )
    assert db_comiss is not None
    assert db_comiss.status == 'aberto'


async def test_create_comiss_only_one_open_per_user(
    client, session, token, users, comiss_data
):
    """Testa que usuario pode ter apenas 1 comissionamento aberto."""
    user, _ = users

    # Cria primeiro comissionamento
    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()

    # Tenta criar segundo comissionamento aberto
    response = await client.post(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
        json=comiss_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'aberto' in resp['message'].lower()


async def test_create_comiss_allows_multiple_if_closed(
    client, session, token, users, comiss_data
):
    """Testa que usuario pode criar novo se anterior estiver fechado."""
    user, _ = users
    today = date.today()

    # Cria comissionamento fechado (periodo anterior)
    comiss_fechado = ComissFactory(
        user_id=user.id,
        status='fechado',
        data_ab=today - timedelta(days=180),
        data_fc=today - timedelta(days=91),
    )
    session.add(comiss_fechado)
    await session.commit()

    # Cria novo comissionamento aberto
    response = await client.post(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
        json=comiss_data,
    )

    assert response.status_code == HTTPStatus.OK


async def test_create_comiss_date_conflict(
    client, session, token, users, comiss_data
):
    """Testa que nao permite criar com conflito de datas."""
    user, _ = users
    today = date.today()

    # Cria comissionamento existente (mesmo periodo)
    comiss_existente = ComissFactory(
        user_id=user.id,
        status='fechado',
        data_ab=today - timedelta(days=30),
        data_fc=today + timedelta(days=30),
    )
    session.add(comiss_existente)
    await session.commit()

    # Tenta criar com datas sobrepostas
    response = await client.post(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
        json=comiss_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'conflito' in resp['message'].lower()


async def test_create_comiss_without_token(client, comiss_data):
    """Testa que requisicao sem token falha."""
    response = await client.post('/cegep/comiss/', json=comiss_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_comiss_missing_required_field(client, token, users):
    """Testa que campo obrigatorio faltando falha."""
    user, _ = users

    # Falta o campo 'doc_aut'
    comiss_data = {
        'user_id': user.id,
        'status': 'aberto',
        'data_ab': date.today().isoformat(),
        'qtd_aj_ab': 30.0,
        'valor_aj_ab': 5000.00,
        'data_fc': (date.today() + timedelta(days=90)).isoformat(),
        'qtd_aj_fc': 30.0,
        'valor_aj_fc': 5000.00,
        'dias_cumprir': 60,
        'doc_prop': 'PROP-0001/2025',
        # doc_aut faltando
    }

    response = await client.post(
        '/cegep/comiss/',
        headers={'Authorization': f'Bearer {token}'},
        json=comiss_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
