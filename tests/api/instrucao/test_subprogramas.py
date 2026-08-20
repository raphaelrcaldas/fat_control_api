"""Cadastro de subprogramas de instrução (/instrucao/subprogramas).

O subprograma é escopado por `uae`: o código é único **dentro** da unidade,
e a função só pode ser uma das que a unidade opera (`funcoes_uae`), mesmo
racional do `proj`/`tenant_projetos`.
"""

from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.models.instrucao.subprogramas import (
    Paop,
    PaopSubprograma,
    Subprograma,
)
from fcontrol_api.models.shared.funcoes import FuncaoUae

pytestmark = pytest.mark.anyio

URL = '/instrucao/subprogramas/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _payload(**over):
    base = {
        'codigo': 'SPFO-01',
        'descricao': 'Formação Piloto Operacional',
        'tipo': 'Formação',
        'func': 'pil',
        'observacoes': None,
    }
    return base | over


@pytest.fixture
async def subprograma_1gt(session):
    """Subprograma de outra org, para os testes de isolamento."""
    subprograma = Subprograma(
        uae='1gt',
        codigo='SPFO-01',
        descricao='Formação Piloto da 1gt',
        tipo='Formação',
        func='pil',
    )
    session.add(subprograma)
    await session.commit()
    return subprograma


async def test_ciclo_completo(client, token):
    criado = await client.post(URL, headers=_auth(token), json=_payload())
    assert criado.status_code == HTTPStatus.CREATED
    subprograma = criado.json()['data']
    assert subprograma['codigo'] == 'SPFO-01'

    listagem = await client.get(URL, headers=_auth(token))
    assert listagem.status_code == HTTPStatus.OK
    assert [s['id'] for s in listagem.json()['data']] == [subprograma['id']]

    editado = await client.put(
        f'{URL}{subprograma["id"]}',
        headers=_auth(token),
        json=_payload(
            codigo='SPMO-01',
            descricao='Manutenção Operacional de Piloto',
            tipo='Manutenção',
            observacoes='  revisado  ',
        ),
    )
    assert editado.status_code == HTTPStatus.OK
    assert editado.json()['data']['codigo'] == 'SPMO-01'
    assert editado.json()['data']['tipo'] == 'Manutenção'
    assert editado.json()['data']['observacoes'] == 'revisado'

    removido = await client.delete(
        f'{URL}{subprograma["id"]}', headers=_auth(token)
    )
    assert removido.status_code == HTTPStatus.OK

    vazia = await client.get(URL, headers=_auth(token))
    assert vazia.json()['data'] == []


async def test_codigo_normaliza_para_maiuscula(client, token):
    resp = await client.post(
        URL, headers=_auth(token), json=_payload(codigo='spfo-02')
    )
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['codigo'] == 'SPFO-02'


@pytest.mark.parametrize(
    'codigo', ['SPF-01', 'SPFO01', 'SPFO-1', 'SPF1-01', 'SPFO-AB']
)
async def test_codigo_fora_do_formato_422(client, token, codigo):
    resp = await client.post(
        URL, headers=_auth(token), json=_payload(codigo=codigo)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_tipo_fora_da_lista_422(client, token):
    resp = await client.post(
        URL, headers=_auth(token), json=_payload(tipo='Reciclagem')
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_codigo_duplicado_na_mesma_org(client, token):
    await client.post(URL, headers=_auth(token), json=_payload())
    resp = await client.post(URL, headers=_auth(token), json=_payload())
    assert resp.status_code == HTTPStatus.CONFLICT
    assert resp.json()['message'] == 'Código já cadastrado nesta organização'


async def test_mesmo_codigo_em_outra_org(client, token, subprograma_1gt):
    """Unicidade é (uae, codigo): a 11gt tem seu próprio SPFO-01."""
    resp = await client.post(URL, headers=_auth(token), json=_payload())
    assert resp.status_code == HTTPStatus.CREATED


async def test_funcao_nao_operada_pela_org(client, session, token):
    await session.execute(
        FuncaoUae.__table__.delete().where(
            FuncaoUae.uae == '11gt', FuncaoUae.func_cod == 'tf'
        )
    )
    await session.commit()

    resp = await client.post(
        URL, headers=_auth(token), json=_payload(func='tf')
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == 'Função não operada pela organização'


@pytest.mark.parametrize('func', ['ml', 'md'])
async def test_funcao_esporadica_recusada(client, token, func):
    """Mestre de lançamento e médico não têm programa de instrução."""
    resp = await client.post(
        URL, headers=_auth(token), json=_payload(func=func)
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == 'Função não operada pela organização'


async def test_funcao_inexistente_no_catalogo(client, token):
    resp = await client.post(
        URL, headers=_auth(token), json=_payload(func='xyz')
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_lista_nao_vaza_de_outra_org(client, token, subprograma_1gt):
    resp = await client.get(URL, headers=_auth(token))
    assert resp.json()['data'] == []


async def test_update_cross_org_404(client, token, subprograma_1gt):
    resp = await client.put(
        f'{URL}{subprograma_1gt.id}',
        headers=_auth(token),
        json=_payload(descricao='Sequestro'),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Subprograma não encontrado'


async def test_delete_cross_org_404(client, token, subprograma_1gt):
    resp = await client.delete(
        f'{URL}{subprograma_1gt.id}', headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_em_paop_409(client, session, token):
    criado = await client.post(URL, headers=_auth(token), json=_payload())
    subprograma_id = criado.json()['data']['id']

    paop = Paop(
        uae='11gt',
        ano=2026,
        data_ini=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
    )
    session.add(paop)
    await session.flush()
    session.add(
        PaopSubprograma(paop_id=paop.id, subprograma_id=subprograma_id)
    )
    await session.commit()

    resp = await client.delete(f'{URL}{subprograma_id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.CONFLICT
    assert 'PAOP' in resp.json()['message']


@pytest.mark.parametrize(
    ('metodo', 'sufixo'),
    [('get', ''), ('post', ''), ('put', '1'), ('delete', '1')],
)
async def test_sem_permissao_403(client, token_sem_perm, metodo, sufixo):
    kwargs = {'headers': _auth(token_sem_perm)}
    if metodo in {'post', 'put'}:
        kwargs['json'] = _payload()

    resp = await getattr(client, metodo)(f'{URL}{sufixo}', **kwargs)
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_sem_token_401(client):
    resp = await client.get(URL)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


async def test_token_sistema_sem_org_400(client, token_sistema):
    """Subprograma é da unidade: sem org ativa não há o que listar."""
    resp = await client.get(URL, headers=_auth(token_sistema))
    assert resp.status_code == HTTPStatus.BAD_REQUEST
