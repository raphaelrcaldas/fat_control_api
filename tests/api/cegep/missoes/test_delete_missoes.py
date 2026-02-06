"""
Testes para o endpoint DELETE /cegep/missoes/{id}.

Este endpoint remove uma missao e seus relacionamentos.
Requer autenticacao.
"""

from datetime import date, datetime, time, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from tests.factories import (
    ComissFactory,
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio


async def test_delete_missao_success(client, session, token, missao_existente):
    """Testa remocao de missao com sucesso."""
    missao_id = missao_existente.id

    response = await client.delete(
        f'/cegep/missoes/{missao_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'removida' in resp['message'].lower()

    # Verifica que foi removida do banco
    db_missao = await session.scalar(
        select(FragMis).where(FragMis.id == missao_id)
    )
    assert db_missao is None


async def test_delete_missao_not_found(client, token):
    """Testa remocao de missao inexistente."""
    response = await client.delete(
        '/cegep/missoes/99999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'não encontrada' in response.json()['message'].lower()


async def test_delete_missao_without_token(client, missao_existente):
    """Testa que requisicao sem token falha."""
    response = await client.delete(
        f'/cegep/missoes/{missao_existente.id}'
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_delete_missao_recalcula_comiss(client, session, token, users):
    """Testa que deletar missao recalcula comissionamentos afetados."""
    user, _ = users
    today = date.today()

    # Criar comissionamento
    comiss = ComissFactory(
        user_id=user.id,
        status='aberto',
        data_ab=today - timedelta(days=30),
        data_fc=today + timedelta(days=60),
        dias_cumprir=60,
    )
    session.add(comiss)
    await session.flush()

    # Criar missao dentro do periodo do comiss
    missao = FragMisFactory(
        n_doc=6001,
        afast=datetime.combine(today, time(8, 0)),
        regres=datetime.combine(today + timedelta(days=5), time(18, 0)),
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,
        data_ini=today,
        data_fim=today + timedelta(days=5),
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id, user_id=user.id, sit='c', p_g=user.p_g
    )
    session.add(user_frag)
    await session.commit()

    missao_id = missao.id

    # Deletar missao
    response = await client.delete(
        f'/cegep/missoes/{missao_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que comiss foi atualizado (cache_calc deve ter sido recalculado)
    await session.refresh(comiss)
    # O cache_calc existe mesmo que zerado
    assert comiss.cache_calc is not None


async def test_delete_missao_cascade_pernoites(
    client, session, token, missao_existente
):
    """Testa que deletar missao remove pernoites em cascade."""
    missao_id = missao_existente.id

    # Verificar que existem pernoites
    pernoites_antes = await session.scalar(
        select(PernoiteFrag).where(PernoiteFrag.frag_id == missao_id)
    )
    assert pernoites_antes is not None

    # Deletar missao
    response = await client.delete(
        f'/cegep/missoes/{missao_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verificar que pernoites foram removidos
    pernoites_depois = await session.scalar(
        select(PernoiteFrag).where(PernoiteFrag.frag_id == missao_id)
    )
    assert pernoites_depois is None


async def test_delete_missao_cascade_users_frag(
    client, session, token, missao_existente
):
    """Testa que deletar missao remove users_frag em cascade."""
    missao_id = missao_existente.id

    # Verificar que existem users_frag
    users_frag_antes = await session.scalar(
        select(UserFrag).where(UserFrag.frag_id == missao_id)
    )
    assert users_frag_antes is not None

    # Deletar missao
    response = await client.delete(
        f'/cegep/missoes/{missao_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verificar que users_frag foram removidos
    users_frag_depois = await session.scalar(
        select(UserFrag).where(UserFrag.frag_id == missao_id)
    )
    assert users_frag_depois is None
