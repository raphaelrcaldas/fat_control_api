"""A convenção de nome de recurso é cobrada pelo schema, não pelo costume.

A base tinha acumulado quatro convenções ao mesmo tempo (`cartoes-saude`,
`dados_bancarios`, `comiss.propostas`, `sebo`) porque nada reprovava um
nome novo fora do padrão. Estes testes existem para que a próxima entropia
falhe na entrada, e não seis meses depois numa auditoria.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.mark.parametrize(
    'nome',
    [
        'users',  # raiz, transversal
        'ops.aeronaves',  # modulo.recurso
        'ops.ordem_missao',  # underscore junta palavras do conceito
        'ops.ordem_missao.status',  # ponto separa nível de hierarquia
        'a.b.c.d.e',  # profundidade livre
    ],
)
async def test_nome_no_padrao_aceito(client, token_sistema, nome):
    resp = await client.post(
        '/security/resources/',
        headers=_auth(token_sistema),
        json={'name': nome, 'description': 'teste'},
    )
    assert resp.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}


@pytest.mark.parametrize(
    'nome',
    [
        'cartoes-saude',  # hífen
        'Ops.Aeronaves',  # maiúscula
        'ops aeronaves',  # espaço
        'ops.',  # segmento vazio
        '.ops',  # começa com ponto
        'ops..aeronaves',  # ponto duplo
        '2ops',  # começa com dígito
    ],
)
async def test_nome_fora_do_padrao_recusado(client, token_sistema, nome):
    resp = await client.post(
        '/security/resources/',
        headers=_auth(token_sistema),
        json={'name': nome, 'description': 'teste'},
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


@pytest.mark.parametrize('nome', ['view', 'create', 'update', 'delete'])
async def test_permissao_no_padrao_aceita(client, token_sistema, nome):
    recurso = await client.post(
        '/security/resources/',
        headers=_auth(token_sistema),
        json={'name': f'teste.{nome}_alvo', 'description': 'teste'},
    )
    resource_id = recurso.json()['data']['id']

    resp = await client.post(
        '/security/permissions/',
        headers=_auth(token_sistema),
        json={
            'resource_id': resource_id,
            'name': nome,
            'description': 'teste',
        },
    )
    assert resp.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}


@pytest.mark.parametrize('nome', ['View', 'read-only', 'ver acesso', 'a.b'])
async def test_permissao_fora_do_padrao_recusada(client, token_sistema, nome):
    resp = await client.post(
        '/security/permissions/',
        headers=_auth(token_sistema),
        json={'resource_id': 1, 'name': nome, 'description': 'teste'},
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
