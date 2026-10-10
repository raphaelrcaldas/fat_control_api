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
        ('patch', '/estatistica/etapas/bulk'),
        ('put', '/estatistica/etapas/1'),
        ('delete', '/estatistica/etapas/1'),
        ('get', '/estatistica/missao/1'),
        ('post', '/estatistica/missao/'),
        ('put', '/estatistica/missao/1'),
        ('delete', '/estatistica/missao/1'),
        ('get', '/estatistica/esfaer/'),
        ('put', '/estatistica/esfaer/'),
        (
            'get',
            '/estatistica/relatorios-voo/'
            '?data_ini=2026-09-01&data_fim=2026-09-30',
        ),
        ('post', '/estatistica/relatorios-voo/'),
        ('get', '/estatistica/relatorios-voo/1/arquivo'),
        ('patch', '/estatistica/relatorios-voo/1'),
        ('delete', '/estatistica/relatorios-voo/1'),
    ],
)
async def test_sem_permissao_403(client, token_sem_perm, metodo, url):
    resp = await getattr(client, metodo)(url, headers=_auth(token_sem_perm))
    assert resp.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    'url',
    [
        '/estatistica/etapas/',
        '/estatistica/missao/1',
        '/estatistica/esfaer/',
        '/estatistica/relatorios-voo/?data_ini=2026-09-01&data_fim=2026-09-30',
    ],
)
async def test_sem_token_401(client, url):
    resp = await client.get(url)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# `TipoMissao` é tabela global: a escrita é do admin de sistema, e nem o
# admin de uma unidade (`token`) pode renomear o código de todas as orgs.
TIPO_MISSAO = {'cod': '99ZZ', 'desc': 'Teste de gate'}


ESCRITAS_TIPO_MISSAO = pytest.mark.parametrize(
    ('metodo', 'url', 'corpo'),
    [
        ('post', '/estatistica/tipo-missao/', TIPO_MISSAO),
        ('put', '/estatistica/tipo-missao/1', {'desc': 'Renomeado'}),
        ('delete', '/estatistica/tipo-missao/1', None),
    ],
)


async def _escrever(client, token, metodo, url, corpo):
    kwargs = {'headers': _auth(token)}
    if corpo is not None:
        kwargs['json'] = corpo
    return await getattr(client, metodo)(url, **kwargs)


@ESCRITAS_TIPO_MISSAO
async def test_tipo_missao_escrita_admin_de_unidade_403(
    client, token, metodo, url, corpo
):
    resp = await _escrever(client, token, metodo, url, corpo)
    assert resp.status_code == HTTPStatus.FORBIDDEN


@ESCRITAS_TIPO_MISSAO
async def test_tipo_missao_escrita_sem_permissao_403(
    client, token_sem_perm, metodo, url, corpo
):
    resp = await _escrever(client, token_sem_perm, metodo, url, corpo)
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_tipo_missao_leitura_livre(client, token_sem_perm):
    """Sem gate de propósito: editor de etapa, simulador e filtros leem."""
    resp = await client.get(
        '/estatistica/tipo-missao/', headers=_auth(token_sem_perm)
    )
    assert resp.status_code == HTTPStatus.OK


async def test_tipo_missao_admin_de_sistema_escreve(client, token_sistema):
    headers = _auth(token_sistema)

    criado = await client.post(
        '/estatistica/tipo-missao/', json=TIPO_MISSAO, headers=headers
    )
    assert criado.status_code == HTTPStatus.CREATED
    tipo_id = criado.json()['data']['id']

    atualizado = await client.put(
        f'/estatistica/tipo-missao/{tipo_id}',
        json={'desc': 'Renomeado'},
        headers=headers,
    )
    assert atualizado.status_code == HTTPStatus.OK
    assert atualizado.json()['data']['desc'] == 'Renomeado'

    removido = await client.delete(
        f'/estatistica/tipo-missao/{tipo_id}', headers=headers
    )
    assert removido.status_code == HTTPStatus.OK
