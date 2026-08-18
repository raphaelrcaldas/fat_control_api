"""Fixtures das propostas de comissionamento."""

import pytest

from tests.factories import UserFactory

URL = '/cegep/propostas/'


def auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def militar_11gt(session):
    """Militar da org ativa dos testes ('11gt'), elegível a entrar em linha."""
    user = UserFactory(unidade='11gt')
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def proposta(client, token):
    """Proposta recém-criada (já nasce com o cenário inicial)."""
    resp = await client.post(
        URL,
        json={'nome': 'Planejamento 2026', 'ano_ref': 2026},
        headers=auth(token),
    )
    assert resp.status_code == 201
    return resp.json()['data']


def payload_com_linhas(proposta, linhas, *, nome=None, cenarios_extras=()):
    """Monta o PUT completo a partir da proposta lida do GET/POST."""
    cenario = proposta['cenarios'][0]
    return {
        'nome': nome or proposta['nome'],
        'ano_ref': proposta['ano_ref'],
        'cenarios': [
            {
                'id': cenario['id'],
                'nome': cenario['nome'],
                'cor': cenario['cor'],
                'linhas': linhas,
            },
            *cenarios_extras,
        ],
    }


def linha(user_id, *, ano_ab=2026, ano_fc=2026, base=1000.0, id=None):
    corpo = {
        'user_id': user_id,
        'base_ab': base,
        'qtd_ab': 2,
        'ano_ab': ano_ab,
        'base_fc': base,
        'qtd_fc': 1,
        'ano_fc': ano_fc,
    }
    if id is not None:
        corpo['id'] = id
    return corpo
