"""Testes do conjunto de funções operado por cada unidade.

`GET /config/funcoes` é a fonte que o front usa para montar seletores;
`PUT` é privativo do admin da org e não pode deixar tripulante ativo
apontando para função que a unidade deixou de operar.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.shared.funcoes import FuncaoUae
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio


def _auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


async def test_list_funcoes_org_traz_as_operadas_ordenadas(client, token):
    response = await client.get('/config/funcoes', headers=_auth(token))

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']

    assert [f['cod'] for f in data] == [
        'pil',
        'oe',
        'mc',
        'lm',
        'tf',
        'os',
        'md',
        'ml',
    ]
    assert data[0]['nome'] == 'Piloto'
    assert data[0]['posicoes'][0]['cod'] == '1P'


async def test_set_funcoes_org_substitui_conjunto(client, session, token):
    response = await client.put(
        '/config/funcoes',
        headers=_auth(token),
        json={'funcoes': [{'cod': 'pil'}, {'cod': 'mc'}]},
    )

    assert response.status_code == HTTPStatus.OK
    assert [f['cod'] for f in response.json()['data']] == ['pil', 'mc']

    persistidas = await session.scalars(
        select(FuncaoUae.func_cod).where(FuncaoUae.uae == '11gt')
    )
    assert set(persistidas) == {'pil', 'mc'}


async def test_set_funcoes_org_aplica_nome_e_ordem_custom(client, token):
    response = await client.put(
        '/config/funcoes',
        headers=_auth(token),
        json={
            'funcoes': [
                {'cod': 'pil', 'ordem': 2},
                {
                    'cod': 'oe',
                    'nome_custom': 'Operador de Sensores',
                    'ordem': 1,
                },
            ]
        },
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']

    # Ordem efetiva da org sobrepõe a do catálogo (pil vinha primeiro).
    assert [f['cod'] for f in data] == ['oe', 'pil']
    assert data[0]['nome'] == 'Operador de Sensores'
    # O rótulo curto continua vindo do catálogo.
    assert data[0]['nome_curto'] == 'OE-3'


async def test_set_funcoes_org_recusa_remover_funcao_em_uso(
    client, session, token
):
    user = UserFactory()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    trip = TripFactory(user_id=user.id, uae='11gt', active=True, func='lm')
    session.add(trip)
    await session.commit()

    response = await client.put(
        '/config/funcoes',
        headers=_auth(token),
        json={'funcoes': [{'cod': 'pil'}]},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'lm' in response.json()['message']

    # Nada foi removido: a rota falha inteira, não pela metade.
    persistidas = await session.scalars(
        select(FuncaoUae.func_cod).where(FuncaoUae.uae == '11gt')
    )
    assert 'lm' in set(persistidas)


async def test_set_funcoes_org_recusa_codigo_fora_do_catalogo(client, token):
    response = await client.put(
        '/config/funcoes',
        headers=_auth(token),
        json={'funcoes': [{'cod': 'pil'}, {'cod': 'nav'}]},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'nav' in response.json()['message']


async def test_set_funcoes_org_recusa_repetida(client, token):
    response = await client.put(
        '/config/funcoes',
        headers=_auth(token),
        json={'funcoes': [{'cod': 'pil'}, {'cod': 'pil'}]},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_set_funcoes_org_exige_admin_da_org(client, token_sem_perm):
    response = await client.put(
        '/config/funcoes',
        headers=_auth(token_sem_perm),
        json={'funcoes': [{'cod': 'pil'}]},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_set_funcoes_org_nao_afeta_outra_unidade(
    client, session, users, make_org_token
):
    """Escrita do admin do 11gt não toca no conjunto do 1gt."""
    user, _ = users
    token_11gt = await make_org_token(user, active_org='11gt')
    token_1gt = await make_org_token(user, active_org='1gt')

    await client.put(
        '/config/funcoes',
        headers=_auth(token_11gt),
        json={'funcoes': [{'cod': 'pil'}]},
    )

    response = await client.get('/config/funcoes', headers=_auth(token_1gt))
    codigos = [f['cod'] for f in response.json()['data']]

    assert len(codigos) == 8
    assert 'lm' in codigos
