"""Projeção de remuneração (/cegep/dados-bancarios/user/{id}/remuneracao).

Endpoint enxuto que serve de base de cálculo às propostas de
comissionamento: devolve só `remuneracao` e `mes_ano`, sem os dados
bancários em volta. Remuneração é PII, então o gate é o mesmo do irmão
`/user/{id}` — owner-OR-`dados_bancarios.view` — e o alvo é escopado por
`User.unidade == active_org` na própria query.

Ausência de dado é resposta normal (200 com `remuneracao: null`), nunca
404: para quem planeja, militar sem remuneração cadastrada é caso comum.
A consequência de segurança é deliberada e está testada aqui — outra org,
usuário inexistente e usuário sem cadastro respondem igual, então a rota
não vira oráculo de enumeração.
"""

from datetime import date
from decimal import Decimal
from http import HTTPStatus

import pytest

from tests.factories import DadosBancariosFactory, UserFactory

pytestmark = pytest.mark.anyio


def _url(user_id: int) -> str:
    return f'/cegep/dados-bancarios/user/{user_id}/remuneracao'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _mk_user_com_remuneracao(session, *, unidade, valor, mes_ano):
    user = UserFactory(unidade=unidade)
    session.add(user)
    await session.flush()

    dados = DadosBancariosFactory(
        user_id=user.id, remuneracao=valor, mes_ano=mes_ano
    )
    session.add(dados)
    await session.flush()
    return user


async def test_com_permissao_devolve_remuneracao(client, session, token):
    """Caminho feliz: só os dois campos, sem banco/agência/conta."""
    alvo = await _mk_user_com_remuneracao(
        session,
        unidade='11gt',
        valor=Decimal('19852.24'),
        mes_ano=date(2026, 4, 1),
    )
    await session.commit()

    resp = await client.get(_url(alvo.id), headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data == {
        'user_id': alvo.id,
        'remuneracao': 19852.24,
        'mes_ano': '2026-04-01',
    }


async def test_sem_cadastro_devolve_nulo(client, session, token):
    """Militar sem dados bancários: 200 com nulo, não 404."""
    alvo = UserFactory(unidade='11gt')
    session.add(alvo)
    await session.commit()

    resp = await client.get(_url(alvo.id), headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['remuneracao'] is None
    assert resp.json()['data']['mes_ano'] is None


async def test_cross_org_nao_vaza_e_nao_enumera(client, session, token):
    """Militar de outra org responde igual a inexistente e a sem cadastro."""
    outro_gt = await _mk_user_com_remuneracao(
        session,
        unidade='1gt',
        valor=Decimal('30000.00'),
        mes_ano=date(2026, 4, 1),
    )
    await session.commit()

    resp = await client.get(_url(outro_gt.id), headers=_auth(token))
    inexistente = await client.get(_url(99999), headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['remuneracao'] is None
    # Byte a byte igual (fora o eco do id): nada distingue os dois casos.
    assert (
        resp.json()['data']['mes_ano'] == inexistente.json()['data']['mes_ano']
    )
    assert (
        resp.json()['data']['remuneracao']
        == inexistente.json()['data']['remuneracao']
    )


async def test_terceiro_sem_permissao_403(client, session, token_sem_perm):
    """Sem `dados_bancarios.view`, remuneração de terceiro é negada."""
    alvo = await _mk_user_com_remuneracao(
        session,
        unidade='11gt',
        valor=Decimal('19852.24'),
        mes_ano=date(2026, 4, 1),
    )
    await session.commit()

    resp = await client.get(_url(alvo.id), headers=_auth(token_sem_perm))

    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_dono_ve_a_propria_sem_permissao(
    client, session, users, token_sem_perm
):
    """O próprio militar lê a sua remuneração sem a permissão (FatBird)."""
    user, _ = users
    dados = DadosBancariosFactory(
        user_id=user.id,
        remuneracao=Decimal('12345.67'),
        mes_ano=date(2026, 4, 1),
    )
    session.add(dados)
    await session.commit()

    resp = await client.get(_url(user.id), headers=_auth(token_sem_perm))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['remuneracao'] == 12345.67
