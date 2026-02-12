"""
Testes para o endpoint DELETE /cegep/diarias/valores/{valor_id}.

Este endpoint deleta um valor de diaria existente.
Requer autenticacao.
"""

from datetime import date, datetime, time, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.diarias import DiariaValor
from tests.factories import (
    DiariaValorFactory,
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio


async def test_delete_diaria_valor_success(
    client, session, token, diaria_valores
):
    """Testa delecao de valor de diaria com sucesso."""
    valor = diaria_valores[0]
    valor_id = valor.id

    response = await client.delete(
        f'/cegep/diarias/valores/{valor_id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert 'deletado com sucesso' in response.json()['message']

    # Verifica no banco
    db_valor = await session.scalar(
        select(DiariaValor).where(DiariaValor.id == valor_id)
    )
    assert db_valor is None


async def test_delete_diaria_valor_not_found(client, token):
    """Testa delecao de valor de diaria inexistente."""
    response = await client.delete(
        '/cegep/diarias/valores/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrado' in response.json()['message']


async def test_delete_diaria_valor_without_token(client, diaria_valores):
    """Testa que requisicao sem token falha."""
    valor = diaria_valores[0]

    response = await client.delete(f'/cegep/diarias/valores/{valor.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_delete_diaria_valor_blocked_by_missao_comiss(
    client, session, token, users
):
    """Testa que nao pode deletar diaria com missao sit=c."""
    user, _ = users
    today = date.today()

    valor = DiariaValorFactory(
        grupo_pg=4,
        grupo_cid=1,
        valor=355.00,
        data_inicio=today - timedelta(days=30),
        data_fim=today + timedelta(days=30),
    )
    session.add(valor)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9001,
        desc='Missao bloqueante',
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
        sit='c',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()
    await session.refresh(valor)

    response = await client.delete(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    msg = response.json()['message']
    assert (
        'missões' in msg.lower()
        or 'diárias' in msg.lower()
    )


async def test_delete_diaria_valor_blocked_by_missao_diaria(
    client, session, token, users
):
    """Testa que nao pode deletar diaria com missao sit=d."""
    user, _ = users
    today = date.today()

    valor = DiariaValorFactory(
        grupo_pg=4,
        grupo_cid=1,
        valor=355.00,
        data_inicio=today - timedelta(days=30),
        data_fim=today + timedelta(days=30),
    )
    session.add(valor)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9002,
        desc='Missao diaria',
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
        sit='d',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()
    await session.refresh(valor)

    response = await client.delete(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CONFLICT


async def test_delete_diaria_valor_allowed_with_grat_only(
    client, session, token, users
):
    """Testa que pode deletar diaria se so tem missao sit=g."""
    user, _ = users
    today = date.today()

    valor = DiariaValorFactory(
        grupo_pg=4,
        grupo_cid=1,
        valor=355.00,
        data_inicio=today - timedelta(days=30),
        data_fim=today + timedelta(days=30),
    )
    session.add(valor)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9003,
        desc='Missao grat',
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
    await session.refresh(valor)

    response = await client.delete(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK


async def test_delete_diaria_valor_allowed_outside_period(
    client, session, token, users
):
    """Testa que pode deletar diaria se missao esta fora."""
    user, _ = users
    today = date.today()

    valor = DiariaValorFactory(
        grupo_pg=4,
        grupo_cid=1,
        valor=355.00,
        data_inicio=today - timedelta(days=60),
        data_fim=today - timedelta(days=31),
    )
    session.add(valor)
    await session.flush()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=9004,
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
        sit='c',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()
    await session.refresh(valor)

    response = await client.delete(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
