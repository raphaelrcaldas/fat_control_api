"""
Testes para o endpoint DELETE /indisp/{id}.

Este endpoint realiza soft delete de uma indisponibilidade.
Requer autenticação.
"""

from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.indisp import Indisp

pytestmark = pytest.mark.anyio


async def test_delete_indisp_success(client, session, indisp, token):
    """Testa soft delete de indisponibilidade com sucesso."""
    response = await client.delete(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {'detail': 'Indisponibilidade deletada'}


async def test_delete_indisp_sets_deleted_at(client, session, indisp, token):
    """Testa que deleted_at é setado após deleção."""
    assert indisp.deleted_at is None

    response = await client.delete(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Recarrega do banco
    await session.refresh(indisp)
    assert indisp.deleted_at is not None


async def test_delete_indisp_not_found(client, token):
    """Testa que ID não existente retorna 404."""
    response = await client.delete(
        '/indisp/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'not found' in response.json()['detail']


async def test_delete_indisp_without_token_fails(client, indisp):
    """Testa que requisição sem token falha."""
    response = await client.delete(f'/indisp/{indisp.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_delete_indisp_already_deleted(client, session, indisp, token):
    """Testa comportamento ao deletar registro já deletado."""
    # Primeira deleção
    response = await client.delete(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    # Segunda deleção (atualiza deleted_at novamente)
    response = await client.delete(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    # O endpoint atual não verifica se já foi deletado
    assert response.status_code == HTTPStatus.OK


async def test_delete_indisp_record_persists_in_db(
    client, session, indisp, token
):
    """Testa que registro persiste no banco após soft delete."""
    indisp_id = indisp.id

    response = await client.delete(
        f'/indisp/{indisp_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que ainda existe no banco
    db_indisp = await session.scalar(
        select(Indisp).where(Indisp.id == indisp_id)
    )
    assert db_indisp is not None
    assert db_indisp.deleted_at is not None
