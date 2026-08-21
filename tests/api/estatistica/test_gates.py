"""Gates dos routers de estatística.

Estes três routers ficaram sem `permission_checker` desde que nasceram: o
front escondia o menu e a API atendia qualquer token válido. Os testes
abaixo travam o buraco — sem eles a regressão volta silenciosa, porque o
sintoma (a tela some) só aparece para quem NÃO é admin.

`sebo` e o simulador seguem sem gate de propósito: o FatBird os consome com
token de tripulante, que não tem role nenhuma.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.parametrize(
    ('metodo', 'url'),
    [
        ('get', '/estatistica/etapas/'),
        ('get', '/estatistica/etapas/1'),
        ('post', '/estatistica/etapas/'),
        ('put', '/estatistica/etapas/1'),
        ('delete', '/estatistica/etapas/1'),
        ('post', '/estatistica/etapas/export'),
        ('get', '/estatistica/missao/1'),
        ('post', '/estatistica/missao/'),
        ('put', '/estatistica/missao/1'),
        ('delete', '/estatistica/missao/1'),
        ('get', '/estatistica/esfaer/'),
        ('put', '/estatistica/esfaer/'),
    ],
)
async def test_sem_permissao_403(client, token_sem_perm, metodo, url):
    resp = await getattr(client, metodo)(url, headers=_auth(token_sem_perm))
    assert resp.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    'url',
    ['/estatistica/etapas/', '/estatistica/missao/1', '/estatistica/esfaer/'],
)
async def test_sem_token_401(client, url):
    resp = await client.get(url)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
