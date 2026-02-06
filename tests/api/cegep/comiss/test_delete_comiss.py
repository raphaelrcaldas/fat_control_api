"""
Testes para o endpoint DELETE /cegep/comiss/{comiss_id}.

Este endpoint deleta um comissionamento.
Requer autenticacao.

Regras de negocio:
- Nao pode deletar comissionamento com missoes vinculadas
"""

from datetime import date, datetime, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from tests.factories import ComissFactory, FragMisFactory, UserFragFactory

pytestmark = pytest.mark.anyio


async def test_delete_comiss_success(client, session, token, users):
    """Testa delecao de comissionamento sem missoes."""
    user, _ = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    comiss_id = comiss.id

    response = await client.delete(
        f'/cegep/comiss/{comiss_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'deletado' in resp['message'].lower()

    # Verifica que foi deletado
    db_comiss = await session.scalar(
        select(Comissionamento).where(Comissionamento.id == comiss_id)
    )
    assert db_comiss is None


async def test_delete_comiss_not_found(client, token):
    """Testa delecao de comissionamento inexistente."""
    response = await client.delete(
        '/cegep/comiss/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'encontrado' in resp['message'].lower()


async def test_delete_comiss_with_missoes_fails(client, session, token, users):
    """Testa que nao permite deletar com missoes vinculadas."""
    user, _ = users
    today = date.today()

    # Cria comissionamento
    comiss = ComissFactory(
        user_id=user.id,
        data_ab=today - timedelta(days=30),
        data_fc=today + timedelta(days=60),
    )
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    # Cria missao dentro do periodo
    afast = datetime.now() - timedelta(days=10)
    regres = datetime.now() - timedelta(days=7)

    missao = FragMisFactory(afast=afast, regres=regres)
    session.add(missao)
    await session.commit()
    await session.refresh(missao)

    # Vincula usuario a missao como comissionado
    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='c',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()

    # Tenta deletar
    response = await client.delete(
        f'/cegep/comiss/{comiss.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'miss' in str(resp['message']).lower()

    # Verifica que nao foi deletado
    db_comiss = await session.scalar(
        select(Comissionamento).where(Comissionamento.id == comiss.id)
    )
    assert db_comiss is not None


async def test_delete_comiss_with_diaria_user_allows(
    client, session, token, users
):
    """Testa que permite deletar mesmo com usuario em situacao diaria."""
    user, _ = users
    today = date.today()

    # Cria comissionamento
    comiss = ComissFactory(
        user_id=user.id,
        data_ab=today - timedelta(days=30),
        data_fc=today + timedelta(days=60),
    )
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    # Cria missao dentro do periodo
    afast = datetime.now() - timedelta(days=10)
    regres = datetime.now() - timedelta(days=7)

    missao = FragMisFactory(afast=afast, regres=regres)
    session.add(missao)
    await session.commit()
    await session.refresh(missao)

    # Vincula usuario a missao como DIARIA (nao comissionado)
    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='d',  # diaria
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()

    comiss_id = comiss.id

    # Deve permitir deletar pois nao ha missao com sit='c'
    response = await client.delete(
        f'/cegep/comiss/{comiss_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que foi deletado
    db_comiss = await session.scalar(
        select(Comissionamento).where(Comissionamento.id == comiss_id)
    )
    assert db_comiss is None


async def test_delete_comiss_without_token(client, session, users):
    """Testa que requisicao sem token falha."""
    user, _ = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    response = await client.delete(f'/cegep/comiss/{comiss.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
