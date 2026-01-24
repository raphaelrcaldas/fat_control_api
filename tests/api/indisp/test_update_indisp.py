"""
Testes para o endpoint PUT /indisp/{id}.

Este endpoint atualiza uma indisponibilidade existente.
Requer autenticação.
Suporta atualizações parciais (campos podem ser None).
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import IndispFactory

pytestmark = pytest.mark.anyio


async def test_update_indisp_success(client, session, indisp, token):
    """Testa atualização de indisponibilidade com sucesso."""
    update_data = {
        'mtv': 'svc',
        'obs': 'Observacao atualizada',
    }

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {'detail': 'Indisponibilidade atualizada'}

    # Verifica no banco
    await session.refresh(indisp)
    assert indisp.mtv == 'svc'
    assert indisp.obs == 'Observacao atualizada'


async def test_update_indisp_partial_update(client, session, indisp, token):
    """Testa que atualização parcial funciona (apenas alguns campos)."""
    original_mtv = indisp.mtv
    original_date_start = indisp.date_start

    update_data = {
        'obs': 'Apenas obs alterada',
    }

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(indisp)
    assert indisp.obs == 'Apenas obs alterada'
    assert indisp.mtv == original_mtv  # Não mudou
    assert indisp.date_start == original_date_start  # Não mudou


async def test_update_indisp_all_fields(client, session, indisp, token):
    """Testa atualização de todos os campos."""
    new_date_start = (date.today() + timedelta(days=10)).isoformat()
    new_date_end = (date.today() + timedelta(days=15)).isoformat()

    update_data = {
        'date_start': new_date_start,
        'date_end': new_date_end,
        'mtv': 'lic',
        'obs': 'Todos campos atualizados',
    }

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(indisp)
    assert indisp.date_start.isoformat() == new_date_start
    assert indisp.date_end.isoformat() == new_date_end
    assert indisp.mtv == 'lic'
    assert indisp.obs == 'Todos campos atualizados'


async def test_update_indisp_not_found(client, token):
    """Testa que ID não existente retorna 404."""
    update_data = {'obs': 'Tentativa'}

    response = await client.put(
        '/indisp/99999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'not found' in response.json()['detail']


async def test_update_indisp_without_token_fails(client, indisp):
    """Testa que requisição sem token falha."""
    update_data = {'obs': 'Sem auth'}

    response = await client.put(f'/indisp/{indisp.id}', json=update_data)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_indisp_duplicate_fails(client, session, users, token):
    """Testa que atualização que cria duplicata falha."""
    user, other_user = users

    # Cria duas indisps diferentes
    indisp1 = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
        obs='Original 1',
    )
    indisp2 = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=date.today() + timedelta(days=10),
        date_end=date.today() + timedelta(days=15),
        mtv='svc',
        obs='Original 2',
    )

    session.add_all([indisp1, indisp2])
    await session.commit()
    await session.refresh(indisp1)
    await session.refresh(indisp2)

    # Tenta atualizar indisp2 para ficar igual a indisp1
    update_data = {
        'date_start': date.today().isoformat(),
        'date_end': (date.today() + timedelta(days=5)).isoformat(),
        'mtv': 'fer',
        'obs': 'Original 1',  # Igual ao indisp1
    }

    response = await client.put(
        f'/indisp/{indisp2.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'já registrada' in response.json()['detail']


async def test_update_indisp_excludes_self_from_duplicate_check(
    client, session, indisp, token
):
    """Testa que próprio registro é excluído da verificação de duplicata."""
    # Atualiza para os mesmos valores (sem alteração real)
    update_data = {
        'date_start': indisp.date_start.isoformat(),
        'date_end': indisp.date_end.isoformat(),
        'mtv': indisp.mtv,
        'obs': indisp.obs,
    }

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    # Não deve dar erro de duplicata
    assert response.status_code == HTTPStatus.OK


async def test_update_indisp_invalid_mtv_fails(client, indisp, token):
    """Testa que mtv inválido falha."""
    update_data = {'mtv': 'invalido'}

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_indisp_empty_payload(client, session, indisp, token):
    """Testa comportamento com payload vazio."""
    original_mtv = indisp.mtv
    original_obs = indisp.obs

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    # Payload vazio é aceito (nenhum campo alterado)
    assert response.status_code == HTTPStatus.OK

    await session.refresh(indisp)
    assert indisp.mtv == original_mtv
    assert indisp.obs == original_obs


async def test_update_indisp_date_fields(client, session, indisp, token):
    """Testa atualização apenas de campos de data."""
    new_date_start = (date.today() + timedelta(days=5)).isoformat()
    new_date_end = (date.today() + timedelta(days=10)).isoformat()

    update_data = {
        'date_start': new_date_start,
        'date_end': new_date_end,
    }

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(indisp)
    assert indisp.date_start.isoformat() == new_date_start
    assert indisp.date_end.isoformat() == new_date_end


async def test_update_indisp_with_explicit_none_value(
    client, session, indisp, token
):
    """Testa que campo explicitamente None é ignorado no update."""
    original_obs = indisp.obs

    # Envia obs explicitamente como None (diferente de não enviar)
    update_data = {
        'obs': None,
        'mtv': 'svc',  # Altera apenas mtv
    }

    response = await client.put(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(indisp)
    # obs não deve mudar porque foi enviado como None
    assert indisp.obs == original_obs
    # mtv deve ter mudado
    assert indisp.mtv == 'svc'
