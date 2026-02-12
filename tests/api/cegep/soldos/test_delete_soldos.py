"""
Testes para o endpoint DELETE /cegep/soldos/{soldo_id}.

Este endpoint deleta um soldo existente.
Requer autenticacao.
"""

from datetime import date, datetime, time, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.public.posto_grad import Soldo
from tests.factories import (
    FragMisFactory,
    PernoiteFragFactory,
    SoldoFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio


async def test_delete_soldo_success(client, session, token, soldos):
    """Testa delecao de soldo com sucesso."""
    soldo = soldos[0]
    soldo_id = soldo.id

    response = await client.delete(
        f'/cegep/soldos/{soldo_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert 'deletado com sucesso' in response.json()['message']

    # Verifica no banco
    db_soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))
    assert db_soldo is None


async def test_delete_soldo_not_found(client, token):
    """Testa delecao de soldo inexistente."""
    response = await client.delete(
        '/cegep/soldos/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Soldo nao encontrado' in response.json()['message']


async def test_delete_soldo_without_token(client, soldos):
    """Testa que requisicao sem token falha."""
    soldo = soldos[0]

    response = await client.delete(f'/cegep/soldos/{soldo.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_delete_soldo_blocked_by_missao_grat(
    client, session, token, users
):
    """Testa que nao pode deletar soldo com missao sit=g."""
    user, _ = users
    today = date.today()

    soldo = SoldoFactory(
        pg='cb',
        valor=3000.00,
        data_inicio=today - timedelta(days=30),
        data_fim=today + timedelta(days=30),
    )
    session.add(soldo)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9010,
        desc='Missao grat bloqueante',
        tipo='adm',
        afast=datetime.combine(today, time(8, 0)),
        regres=datetime.combine(
            today + timedelta(days=3), time(18, 0)
        ),
        acrec_desloc=False,
        obs='',
        indenizavel=True,
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,
        data_ini=today,
        data_fim=today + timedelta(days=3),
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='g',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()
    await session.refresh(soldo)

    response = await client.delete(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    msg = response.json()['message']
    assert (
        'missões' in msg.lower()
        or 'gratificação' in msg.lower()
    )


async def test_delete_soldo_allowed_with_comiss_only(
    client, session, token, users
):
    """Testa que pode deletar soldo se so tem missao sit=c."""
    user, _ = users
    today = date.today()

    soldo = SoldoFactory(
        pg='cb',
        valor=3000.00,
        data_inicio=today - timedelta(days=30),
        data_fim=today + timedelta(days=30),
    )
    session.add(soldo)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9011,
        desc='Missao comiss',
        tipo='adm',
        afast=datetime.combine(today, time(8, 0)),
        regres=datetime.combine(
            today + timedelta(days=2), time(18, 0)
        ),
        acrec_desloc=False,
        obs='',
        indenizavel=True,
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,
        data_ini=today,
        data_fim=today + timedelta(days=2),
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='c',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()
    await session.refresh(soldo)

    response = await client.delete(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK


async def test_delete_soldo_allowed_outside_period(
    client, session, token, users
):
    """Testa que pode deletar soldo se missao esta fora."""
    user, _ = users
    today = date.today()

    soldo = SoldoFactory(
        pg='cb',
        valor=3000.00,
        data_inicio=today - timedelta(days=60),
        data_fim=today - timedelta(days=31),
    )
    session.add(soldo)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9012,
        desc='Missao futura',
        tipo='adm',
        afast=datetime.combine(today, time(8, 0)),
        regres=datetime.combine(
            today + timedelta(days=2), time(18, 0)
        ),
        acrec_desloc=False,
        obs='',
        indenizavel=True,
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,
        data_ini=today,
        data_fim=today + timedelta(days=2),
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='g',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()
    await session.refresh(soldo)

    response = await client.delete(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
