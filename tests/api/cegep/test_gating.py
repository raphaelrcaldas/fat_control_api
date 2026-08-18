"""Gating RBAC do módulo CEGEP (trava de regressão).

Cada rota do CEGEP exige permissão no recurso correspondente
(`comiss`, `missoes_cegep`, `orcamento`, `dados_bancarios`). O `token_sem_perm`
é um usuário autenticado cujo único vínculo admin é de SISTEMA (org NULL);
com a org ativa '11gt' ele não é admin nem tem grant → toda rota gateada
responde 403.

Se um gate for removido por engano, o respectivo caso aqui quebra.

Soldos e Diárias saíram do CEGEP para o escopo Admin de sistema — o gate
deles é testado em tests/api/admin/test_gating.py.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio

# (método, url) de rotas gateadas — escolhidas sem corpo (GET/DELETE) para
# exercitar a dependência de permissão sem esbarrar em validação 422.
GATED = [
    ('GET', '/cegep/comiss/'),
    ('DELETE', '/cegep/comiss/99999'),
    ('GET', '/cegep/missoes/'),
    ('DELETE', '/cegep/missoes/99999'),
    ('GET', '/cegep/financeiro/pgts'),
    ('GET', '/cegep/orcamento/'),
    ('GET', '/cegep/dados-bancarios/'),
    ('DELETE', '/cegep/dados-bancarios/99999'),
    # Propostas reusam o recurso `comiss`: são simulação sobre o mesmo teto.
    ('GET', '/cegep/propostas/'),
    ('GET', '/cegep/propostas/99999'),
    ('DELETE', '/cegep/propostas/99999'),
]


@pytest.mark.parametrize(('method', 'url'), GATED)
async def test_cegep_route_forbidden_without_permission(
    client, token_sem_perm, method, url
):
    """Sem grant na org ativa '11gt' → 403 em toda rota CEGEP gateada."""
    response = await client.request(
        method, url, headers={'Authorization': f'Bearer {token_sem_perm}'}
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(('method', 'url'), GATED)
async def test_cegep_route_requires_token(client, method, url):
    """Sem token → 401 (middleware de autenticação global)."""
    response = await client.request(method, url)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


# Escrita de proposta fica fora da lista acima porque exige corpo válido —
# sem ele o 422 mascararia a ausência do gate.
ESCRITA_PROPOSTA = [
    ('POST', '/cegep/propostas/', {'nome': 'X', 'ano_ref': 2026}),
    (
        'PUT',
        '/cegep/propostas/99999',
        {'nome': 'X', 'ano_ref': 2026, 'cenarios': []},
    ),
]


@pytest.mark.parametrize(('method', 'url', 'corpo'), ESCRITA_PROPOSTA)
async def test_escrita_de_proposta_gateada(
    client, token_sem_perm, method, url, corpo
):
    """`create`/`update` de proposta também exigem grant em `comiss`."""
    response = await client.request(
        method,
        url,
        json=corpo,
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
