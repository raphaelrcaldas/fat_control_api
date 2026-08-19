"""Testes do catálogo global de funções (GET /funcoes).

O catálogo é semeado pela migration `a826ee3bcd9e`, com as 8 funções que
antes viviam num Literal no código.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.shared.funcoes import Funcao

pytestmark = pytest.mark.anyio


async def test_list_funcoes_traz_catalogo_com_posicoes(client, token):
    response = await client.get(
        '/funcoes/', headers={'Authorization': f'Bearer {token}'}
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']

    codigos = [f['cod'] for f in data]
    assert codigos == ['pil', 'oe', 'mc', 'lm', 'tf', 'os', 'md', 'ml']

    piloto = data[0]
    assert piloto['nome'] == 'Piloto'
    assert piloto['cor'] == 'blue'
    assert [p['cod'] for p in piloto['posicoes']] == [
        '1P',
        '2P',
        'IN',
        'AL',
        'O3',
    ]
    assert piloto['posicoes'][2]['tipo'] == 'instrutor'

    # Função esporádica não tem posição a bordo (era o caso de ml/md).
    esporadicas = [f for f in data if f['esporadica']]
    assert {f['cod'] for f in esporadicas} == {'md', 'ml'}
    assert all(f['posicoes'] == [] for f in esporadicas)


async def test_list_funcoes_esconde_inativa_por_padrao(client, session, token):
    funcao = await session.scalar(select(Funcao).where(Funcao.cod == 'ml'))
    funcao.active = False
    await session.commit()

    try:
        response = await client.get(
            '/funcoes/', headers={'Authorization': f'Bearer {token}'}
        )
        assert 'ml' not in [f['cod'] for f in response.json()['data']]

        com_inativas = await client.get(
            '/funcoes/',
            params={'incluir_inativas': True},
            headers={'Authorization': f'Bearer {token}'},
        )
        assert 'ml' in [f['cod'] for f in com_inativas.json()['data']]
    finally:
        funcao.active = True
        await session.commit()


async def test_list_funcoes_exige_token(client):
    response = await client.get('/funcoes/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
