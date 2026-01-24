"""
Testes para o endpoint POST /indisp/.

Este endpoint cria uma nova indisponibilidade.
Requer autenticação.
"""

from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.enums.indisp import IndispEnum
from fcontrol_api.models.public.indisp import Indisp
from tests.factories import IndispFactory

pytestmark = pytest.mark.anyio


async def test_create_indisp_success(client, session, users, token):
    """Testa criação de indisponibilidade com sucesso."""
    _, other_user = users

    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'fer',
        'obs': 'Ferias programadas',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        'detail': 'Indisponibilidade adicionada com sucesso'
    }

    # Verifica no banco
    db_indisp = await session.scalar(
        select(Indisp).where(Indisp.user_id == other_user.id)
    )
    assert db_indisp is not None
    assert db_indisp.mtv == 'fer'
    assert db_indisp.obs == 'Ferias programadas'


async def test_create_indisp_sets_created_by(client, session, users, token):
    """Testa que created_by é setado para o usuário autenticado."""
    user, other_user = users

    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=3)).isoformat(),
        'mtv': 'svc',
        'obs': 'Servico',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.CREATED

    db_indisp = await session.scalar(
        select(Indisp).where(Indisp.user_id == other_user.id)
    )
    assert db_indisp.created_by == user.id


async def test_create_indisp_date_end_before_date_start_fails(
    client, users, token
):
    """Testa que date_end antes de date_start falha."""
    _, other_user = users

    indisp_data = {
        'user_id': other_user.id,
        'date_start': (date.today() + timedelta(days=5)).isoformat(),
        'date_end': date.today().isoformat(),
        'mtv': 'fer',
        'obs': 'Teste invalido',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data Fim deve ser maior ou igual' in response.json()['detail']


async def test_create_indisp_same_dates_success(client, session, users, token):
    """Testa que date_end igual a date_start é válido."""
    _, other_user = users

    today = date.today().isoformat()

    indisp_data = {
        'user_id': other_user.id,
        'date_start': today,
        'date_end': today,
        'mtv': 'sde',
        'obs': 'Consulta medica',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_indisp_duplicate_fails(client, session, users, token):
    """Testa que duplicata (mesmo user_id, datas e mtv) falha."""
    user, other_user = users

    # Cria uma indisp existente
    existing = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    session.add(existing)
    await session.commit()

    # Tenta criar duplicata
    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'fer',
        'obs': 'Duplicata',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'já registrada' in response.json()['detail']


async def test_create_indisp_same_dates_different_mtv_success(
    client, session, users, token
):
    """Testa que mesmas datas com mtv diferente não é duplicata."""
    user, other_user = users

    # Cria uma indisp existente com mtv='fer'
    existing = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    session.add(existing)
    await session.commit()

    # Cria nova com mtv diferente
    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'svc',
        'obs': 'Motivo diferente',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_indisp_deleted_record_not_duplicate(
    client, session, users, token
):
    """Testa que registro soft-deleted não é considerado duplicata."""
    user, other_user = users

    # Cria uma indisp e marca como deletada
    deleted = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    session.add(deleted)
    await session.commit()

    deleted.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    # Cria nova com mesmos dados
    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'fer',
        'obs': 'Recriado apos deleção',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.CREATED


async def test_create_indisp_without_token_fails(client, users):
    """Testa que requisição sem token falha."""
    _, other_user = users

    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'fer',
        'obs': 'Sem autenticacao',
    }

    response = await client.post('/indisp/', json=indisp_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_indisp_invalid_mtv_fails(client, users, token):
    """Testa que mtv inválido falha."""
    _, other_user = users

    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'invalido',
        'obs': 'Motivo invalido',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_indisp_missing_required_field_fails(
    client, users, token
):
    """Testa que campo obrigatório faltando falha."""
    _, other_user = users

    # Falta o campo 'obs'
    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'fer',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize('mtv', [e.value for e in IndispEnum])
async def test_create_indisp_all_mtv_values_accepted(
    client, session, users, token, mtv
):
    """Testa que todos os valores de IndispEnum são aceitos."""
    _, other_user = users

    indisp_data = {
        'user_id': other_user.id,
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=1)).isoformat(),
        'mtv': mtv,
        'obs': f'Teste mtv {mtv}',
    }

    response = await client.post(
        '/indisp/',
        headers={'Authorization': f'Bearer {token}'},
        json=indisp_data,
    )

    assert response.status_code == HTTPStatus.CREATED

    # Limpa para o próximo teste parametrizado
    db_indisp = await session.scalar(
        select(Indisp).where(
            Indisp.user_id == other_user.id, Indisp.mtv == mtv
        )
    )
    if db_indisp:
        await session.delete(db_indisp)
        await session.commit()
