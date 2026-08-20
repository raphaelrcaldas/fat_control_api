"""Testes do CRUD do catálogo de funções (admin de sistema).

O catálogo é control-plane: quem mexe é o admin de sistema (token sem org
ativa). Admin de unidade escolhe o que opera, mas não inventa função.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.instrucao.subprogramas import Subprograma
from fcontrol_api.models.shared.funcoes import (
    Funcao,
    FuncaoPosicao,
    FuncaoUae,
)
from fcontrol_api.models.shared.quads import QuadsFunc
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio


def _auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


async def test_admin_lista_catalogo_inclusive_inativas(
    client, session, token_sistema
):
    funcao = await session.scalar(select(Funcao).where(Funcao.cod == 'ml'))
    funcao.active = False
    await session.commit()

    try:
        response = await client.get(
            '/admin/funcoes/', headers=_auth(token_sistema)
        )
        assert response.status_code == HTTPStatus.OK
        assert 'ml' in [f['cod'] for f in response.json()['data']]
    finally:
        funcao.active = True
        await session.commit()


async def test_admin_cria_funcao(client, session, token_sistema):
    response = await client.post(
        '/admin/funcoes/',
        headers=_auth(token_sistema),
        json={
            'cod': 'nav',
            'nome': 'Navegador',
            'nome_curto': 'Nav',
            'cor': 'cyan',
            'ordem': 9,
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['data']['cod'] == 'nav'

    criada = await session.get(Funcao, 'nav')
    assert criada is not None
    await session.delete(criada)
    await session.commit()


async def test_admin_recusa_codigo_duplicado(client, token_sistema):
    response = await client.post(
        '/admin/funcoes/',
        headers=_auth(token_sistema),
        json={
            'cod': 'pil',
            'nome': 'Piloto',
            'nome_curto': 'Piloto',
            'cor': 'blue',
            'ordem': 1,
        },
    )

    assert response.status_code == HTTPStatus.CONFLICT


async def test_admin_atualiza_funcao(client, session, token_sistema):
    response = await client.put(
        '/admin/funcoes/os',
        headers=_auth(token_sistema),
        json={
            'nome': 'Observador SAR',
            'nome_curto': 'ObsSAR',
            'cor': 'red',
            'ordem': 6,
            'esporadica': False,
            'active': True,
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['nome'] == 'Observador SAR'

    funcao = await session.scalar(select(Funcao).where(Funcao.cod == 'os'))
    await session.refresh(funcao)
    funcao.nome = 'Observador-SAR'
    funcao.nome_curto = 'Obs-SAR'
    await session.commit()


async def test_admin_substitui_posicoes(client, session, token_sistema):
    response = await client.put(
        '/admin/funcoes/ml/posicoes',
        headers=_auth(token_sistema),
        json={
            'posicoes': [
                {'cod': 'ml', 'nome': 'Mestre', 'ordem': 1},
                {
                    'cod': 'im',
                    'nome': 'Instrutor',
                    'tipo': 'instrutor',
                    'ordem': 2,
                },
            ]
        },
    )

    assert response.status_code == HTTPStatus.OK
    assert [p['cod'] for p in response.json()['data']['posicoes']] == [
        'ML',
        'IM',
    ]

    await session.execute(
        FuncaoPosicao.__table__.delete().where(FuncaoPosicao.func_cod == 'ml')
    )
    await session.commit()


async def test_admin_recusa_posicoes_repetidas(client, token_sistema):
    response = await client.put(
        '/admin/funcoes/ml/posicoes',
        headers=_auth(token_sistema),
        json={
            'posicoes': [
                {'cod': 'ml', 'nome': 'Mestre', 'ordem': 1},
                {'cod': 'ML', 'nome': 'Duplicada', 'ordem': 2},
            ]
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_admin_recusa_excluir_funcao_em_uso(
    client, session, token_sistema
):
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip = TripFactory(user_id=user.id, uae='11gt', active=True, func='tf')
    session.add(trip)
    await session.commit()

    response = await client.delete(
        '/admin/funcoes/tf', headers=_auth(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'tripulante' in response.json()['message'].lower()


async def test_admin_recusa_excluir_funcao_de_subprograma(
    client, session, token_sistema
):
    """Sem este guard a FK do subprograma estouraria como 500 no commit."""
    # Zera os guards anteriores: o que tem de barrar aqui é o subprograma.
    await session.execute(
        FuncaoUae.__table__.delete().where(FuncaoUae.func_cod == 'tf')
    )
    await session.execute(
        QuadsFunc.__table__.delete().where(QuadsFunc.func == 'tf')
    )
    session.add(
        Subprograma(
            uae='11gt',
            codigo='SPFO-09',
            descricao='Formação de tripulante técnico',
            tipo='Formação',
            func='tf',
        )
    )
    await session.commit()

    response = await client.delete(
        '/admin/funcoes/tf', headers=_auth(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'subprograma' in response.json()['message'].lower()


async def test_admin_de_unidade_nao_gerencia_catalogo(client, token):
    """Admin da org tem bypass na org, não no control-plane de sistema."""
    response = await client.post(
        '/admin/funcoes/',
        headers=_auth(token),
        json={
            'cod': 'nav',
            'nome': 'Navegador',
            'nome_curto': 'Nav',
            'cor': 'cyan',
            'ordem': 9,
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
