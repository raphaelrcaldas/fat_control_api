"""Gating de sistema do escopo Admin (trava de regressão).

Soldos e Diárias são control-plane de sistema: o grupo `/admin` aplica
`require_system_admin` uma única vez. Só o admin de SISTEMA (contexto
Sistema, active_org NULL — a fixture `token`) acessa; qualquer outro
contexto responde 403 SCOPE_FORBIDDEN.

O `org_token` tem vínculo admin de sistema (org NULL) mas está com a org
ativa '11gt' — logo NÃO é admin de sistema naquele contexto e deve ser
barrado. Se o gate do grupo cair, estes casos quebram.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio

# (método, url) de rotas do grupo /admin — sem corpo (GET/DELETE) para
# exercitar o gate sem esbarrar em validação 422.
GATED = [
    ('GET', '/admin/soldos/'),
    ('DELETE', '/admin/soldos/99999'),
    ('GET', '/admin/diarias/valores/'),
    ('DELETE', '/admin/diarias/valores/99999'),
]


@pytest.mark.parametrize(('method', 'url'), GATED)
async def test_admin_route_forbidden_outside_system(
    client, org_token, method, url
):
    """Com org ativa '11gt' (não é admin de sistema) → 403."""
    response = await client.request(
        method, url, headers={'Authorization': f'Bearer {org_token}'}
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(('method', 'url'), GATED)
async def test_admin_route_requires_token(client, method, url):
    """Sem token → 401 (middleware de autenticação global)."""
    response = await client.request(method, url)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
