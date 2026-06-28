"""Gating RBAC do módulo CEGEP (trava de regressão).

Cada rota do CEGEP exige permissão no recurso correspondente
(`comiss`, `missoes_cegep`, `orcamento`, `soldo`, `diaria`,
`dados_bancarios`). O `org_token` é um usuário autenticado cujo único
vínculo admin é de SISTEMA (org NULL); com a org ativa '11gt' ele não é
admin nem tem grant → toda rota gateada responde 403.

Se um gate for removido por engano, o respectivo caso aqui quebra.
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
    ('GET', '/cegep/soldos/'),
    ('DELETE', '/cegep/soldos/99999'),
    ('GET', '/cegep/diarias/valores/'),
    ('DELETE', '/cegep/diarias/valores/99999'),
    ('GET', '/cegep/dados-bancarios/'),
    ('DELETE', '/cegep/dados-bancarios/99999'),
]


@pytest.mark.parametrize(('method', 'url'), GATED)
async def test_cegep_route_forbidden_without_permission(
    client, org_token, method, url
):
    """Sem grant na org ativa '11gt' → 403 em toda rota CEGEP gateada."""
    response = await client.request(
        method, url, headers={'Authorization': f'Bearer {org_token}'}
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(('method', 'url'), GATED)
async def test_cegep_route_requires_token(client, method, url):
    """Sem token → 401 (middleware de autenticação global)."""
    response = await client.request(method, url)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
