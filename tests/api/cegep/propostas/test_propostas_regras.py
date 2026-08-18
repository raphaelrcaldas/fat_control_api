"""Regras de domínio e isolamento cross-org das propostas.

Toda regra aqui existe em dois lugares: no schema (que devolve 422 com a
frase certa) e como CHECK/UNIQUE na tabela (rede de segurança). Sem a
validação no schema, cada uma delas chegava ao usuário como 500.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole
from tests.api.cegep.propostas.conftest import (
    URL,
    auth,
    linha,
    payload_com_linhas,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def token_1gt(users, session, make_org_token):
    """Token de outra organização, para provar o isolamento."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def test_abertura_fora_do_exercicio_da_proposta(
    client, token, proposta, militar_11gt
):
    """Decisão do dono: não existe linha que comece fora do `ano_ref`."""
    resp = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(
            proposta, [linha(militar_11gt.id, ano_ab=2027, ano_fc=2027)]
        ),
        headers=auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'exercício da proposta' in resp.text


async def test_fechamento_antes_da_abertura(
    client, token, proposta, militar_11gt
):
    resp = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(
            proposta, [linha(militar_11gt.id, ano_ab=2026, ano_fc=2025)]
        ),
        headers=auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_militar_repetido_no_mesmo_cenario(
    client, token, proposta, militar_11gt
):
    """Violaria o UNIQUE — tem de sair como 422, não como 500."""
    resp = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(
            proposta, [linha(militar_11gt.id), linha(militar_11gt.id)]
        ),
        headers=auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'duas vezes' in resp.text


async def test_mesmo_militar_em_cenarios_diferentes_e_permitido(
    client, token, proposta, militar_11gt
):
    """Comparar cenários exige o mesmo militar nos dois."""
    resp = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(
            proposta,
            [linha(militar_11gt.id)],
            cenarios_extras=[
                {
                    'nome': 'Ampliado',
                    'cor': 'violet',
                    'linhas': [linha(militar_11gt.id)],
                }
            ],
        ),
        headers=auth(token),
    )

    assert resp.status_code == HTTPStatus.OK


@pytest.mark.parametrize('qtd', [0, 3, 0.7])
async def test_qtd_ajuda_fora_da_lista_fechada(
    client, token, proposta, militar_11gt, qtd
):
    """Mesma regra do `ComissForm`: {0,5 | 1 | 1,5 | 2}."""
    corpo = payload_com_linhas(proposta, [linha(militar_11gt.id)])
    corpo['cenarios'][0]['linhas'][0]['qtd_ab'] = qtd

    resp = await client.put(
        f'{URL}{proposta["id"]}', json=corpo, headers=auth(token)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_cor_fora_da_paleta(client, token, proposta):
    corpo = payload_com_linhas(proposta, [])
    corpo['cenarios'][0]['cor'] = 'chartreuse'

    resp = await client.put(
        f'{URL}{proposta["id"]}', json=corpo, headers=auth(token)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_militar_de_outra_org_nao_entra(
    client, token, proposta, session
):
    """O gate autoriza a ação; o alvo é conferido na query."""
    forasteiro = UserFactory(unidade='1gt')
    session.add(forasteiro)
    await session.commit()

    resp = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, [linha(forasteiro.id)]),
        headers=auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_proposta_de_outra_org_nao_e_lida_nem_alterada(
    client, token, token_1gt, proposta
):
    """Proposta da '11gt' não existe para quem está na '1gt'."""
    leitura = await client.get(
        f'{URL}{proposta["id"]}', headers=auth(token_1gt)
    )
    escrita = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, []),
        headers=auth(token_1gt),
    )
    exclusao = await client.delete(
        f'{URL}{proposta["id"]}', headers=auth(token_1gt)
    )
    lista = await client.get(URL, headers=auth(token_1gt))

    assert leitura.status_code == HTTPStatus.NOT_FOUND
    assert escrita.status_code == HTTPStatus.NOT_FOUND
    assert exclusao.status_code == HTTPStatus.NOT_FOUND
    assert proposta['id'] not in [p['id'] for p in lista.json()['data']]
