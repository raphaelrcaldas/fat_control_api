"""CRUD de grupos e tipos de quadrinho (/ops/quads/groups e /types).

Todas as rotas de escrita têm o gate `ops.quadrinhos.create` (inclusive PUT e
DELETE) e o alvo é escopado pela org ativa: grupo por `QuadsGroup.uae`, tipo
pelo grupo ao qual pertence. Os testes de acesso cruzado conferem, no banco,
que nada foi alterado nem removido.

O seed faz as duas orgs operarem todas as funções de
`tests/seed/funcoes.py::CODIGOS`; os testes de 400 montam o próprio recorte
(a '11gt' deixa de operar `md` e desativa `ml`).
"""

from http import HTTPStatus

import pytest
from sqlalchemy import delete, select, update

from fcontrol_api.models.shared.funcoes import FuncaoUae
from fcontrol_api.models.shared.quads import (
    Quad,
    QuadsFunc,
    QuadsGroup,
    QuadsType,
)
from tests.factories import QuadFactory

pytestmark = pytest.mark.anyio

BASE = '/ops/quads'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _mk_group(session, uae, short='gx', long='grupo x'):
    group = QuadsGroup(short=short, long=long, uae=uae)
    session.add(group)
    await session.commit()
    return group


async def _mk_type(session, group_id, funcs=(), short='tx', long='tipo x'):
    type_db = QuadsType(group_id=group_id, short=short, long=long)
    session.add(type_db)
    await session.flush()
    session.add_all([QuadsFunc(type_id=type_db.id, func=f) for f in funcs])
    await session.commit()
    return type_db


async def _fresh(session, model, pk):
    """Relê a linha do banco ignorando o identity map da sessão."""
    return await session.scalar(
        select(model)
        .where(model.id == pk)
        .execution_options(populate_existing=True)
    )


async def _funcs(session, type_id):
    rows = await session.scalars(
        select(QuadsFunc.func).where(QuadsFunc.type_id == type_id)
    )
    return sorted(rows)


@pytest.fixture
async def own(session):
    """Grupo e tipo (com funções pil/mc) da '11gt'."""
    group = await _mk_group(session, '11gt', 'g11', 'grupo da 11gt')
    type_db = await _mk_type(
        session, group.id, ('pil', 'mc'), 't11', 'tipo da 11gt'
    )
    return group.id, type_db.id


@pytest.fixture
async def alien(session):
    """Grupo vazio e tipo (com funções pil/mc) em outro grupo, ambos da '1gt'.

    O grupo vazio permite provar que o DELETE não é barrado pelo 409.
    """
    empty = await _mk_group(session, '1gt', 'g1e', 'grupo vazio da 1gt')
    group = await _mk_group(session, '1gt', 'g1', 'grupo da 1gt')
    type_db = await _mk_type(
        session, group.id, ('pil', 'mc'), 't1', 'tipo da 1gt'
    )
    return empty.id, group.id, type_db.id


# ---------------------------------------------------------------------------
# Gate: token sem permissão -> 403, e nada muda
# ---------------------------------------------------------------------------

GATED = [
    ('POST', '/groups', {'short': 'n', 'long': 'novo'}),
    ('PUT', '/groups/{g}', {'short': 'mudou'}),
    ('DELETE', '/groups/{g}', None),
    ('POST', '/groups/{g}/types', {'short': 'n', 'long': 'novo'}),
    ('PUT', '/types/{t}', {'short': 'mudou'}),
    ('DELETE', '/types/{t}', None),
    ('PUT', '/types/{t}/funcs', {'funcs': ['oe']}),
]


@pytest.mark.parametrize(
    ('method', 'path', 'body'),
    GATED,
    ids=[f'{m} {p}' for m, p, _ in GATED],
)
async def test_escrita_sem_permissao_403(
    client, session, token_sem_perm, own, method, path, body
):
    group_id, type_id = own
    resp = await client.request(
        method,
        BASE + path.format(g=group_id, t=type_id),
        json=body,
        headers=_auth(token_sem_perm),
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN

    group = await _fresh(session, QuadsGroup, group_id)
    type_db = await _fresh(session, QuadsType, type_id)
    assert (group.short, group.long) == ('g11', 'grupo da 11gt')
    assert (type_db.short, type_db.long) == ('t11', 'tipo da 11gt')
    assert await _funcs(session, type_id) == ['mc', 'pil']
    novo_grupo = await session.scalar(
        select(QuadsGroup.id).where(QuadsGroup.short == 'n')
    )
    assert novo_grupo is None
    novo_tipo = await session.scalar(
        select(QuadsType.id).where(QuadsType.short == 'n')
    )
    assert novo_tipo is None


async def test_escrita_sem_token_401(client):
    resp = await client.post(
        f'{BASE}/groups', json={'short': 'n', 'long': 'novo'}
    )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# ---------------------------------------------------------------------------
# Isolamento por org: alvo de outra org -> 404 e nada alterado
# ---------------------------------------------------------------------------


async def test_put_group_de_outra_org_404(client, session, token, alien):
    _, group_id, _ = alien

    resp = await client.put(
        f'{BASE}/groups/{group_id}',
        json={'short': 'invadido', 'long': 'invadido'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Grupo de quadrinhos não encontrado'
    group = await _fresh(session, QuadsGroup, group_id)
    assert (group.short, group.long, group.uae) == (
        'g1',
        'grupo da 1gt',
        '1gt',
    )


async def test_delete_group_de_outra_org_404(client, session, token, alien):
    empty_id, _, _ = alien

    resp = await client.delete(
        f'{BASE}/groups/{empty_id}', headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Grupo de quadrinhos não encontrado'
    assert await _fresh(session, QuadsGroup, empty_id) is not None


async def test_post_type_em_group_de_outra_org_404(
    client, session, token, alien
):
    _, group_id, _ = alien

    resp = await client.post(
        f'{BASE}/groups/{group_id}/types',
        json={'short': 'inv', 'long': 'invadido'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Grupo de quadrinhos não encontrado'
    criado = await session.scalar(
        select(QuadsType.id).where(QuadsType.short == 'inv')
    )
    assert criado is None


async def test_put_type_de_outra_org_404(client, session, token, alien):
    _, _, type_id = alien

    resp = await client.put(
        f'{BASE}/types/{type_id}',
        json={'short': 'invadido', 'long': 'invadido'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Tipo de quadrinho não encontrado'
    type_db = await _fresh(session, QuadsType, type_id)
    assert (type_db.short, type_db.long) == ('t1', 'tipo da 1gt')


async def test_delete_type_de_outra_org_404(client, session, token, alien):
    _, _, type_id = alien

    resp = await client.delete(f'{BASE}/types/{type_id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Tipo de quadrinho não encontrado'
    assert await _fresh(session, QuadsType, type_id) is not None
    assert await _funcs(session, type_id) == ['mc', 'pil']


async def test_put_funcs_de_type_de_outra_org_404(
    client, session, token, alien
):
    _, _, type_id = alien

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': ['oe']},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Tipo de quadrinho não encontrado'
    assert await _funcs(session, type_id) == ['mc', 'pil']


async def test_ids_inexistentes_404(client, token):
    headers = _auth(token)
    grupo = 'Grupo de quadrinhos não encontrado'
    tipo = 'Tipo de quadrinho não encontrado'
    chamadas = [
        (client.put(f'{BASE}/groups/999999', json={}, headers=headers), grupo),
        (client.delete(f'{BASE}/groups/999999', headers=headers), grupo),
        (
            client.post(
                f'{BASE}/groups/999999/types',
                json={'short': 'a', 'long': 'a'},
                headers=headers,
            ),
            grupo,
        ),
        (client.put(f'{BASE}/types/999999', json={}, headers=headers), tipo),
        (client.delete(f'{BASE}/types/999999', headers=headers), tipo),
        (
            client.put(
                f'{BASE}/types/999999/funcs',
                json={'funcs': []},
                headers=headers,
            ),
            tipo,
        ),
    ]

    for chamada, mensagem in chamadas:
        resp = await chamada
        assert resp.status_code == HTTPStatus.NOT_FOUND
        assert resp.json()['message'] == mensagem


async def test_create_group_grava_org_ativa_ignorando_corpo(
    client, session, token, admin_1gt_token
):
    """`uae` vem da org ativa do token, nunca do corpo."""
    resp_11 = await client.post(
        f'{BASE}/groups',
        json={'short': 'a11', 'long': 'a 11gt', 'uae': '1gt'},
        headers=_auth(token),
    )
    resp_1 = await client.post(
        f'{BASE}/groups',
        json={'short': 'a1', 'long': 'a 1gt', 'uae': '11gt'},
        headers=_auth(admin_1gt_token),
    )

    assert resp_11.status_code == HTTPStatus.CREATED
    assert resp_1.status_code == HTTPStatus.CREATED
    g11 = await _fresh(session, QuadsGroup, resp_11.json()['data']['id'])
    g1 = await _fresh(session, QuadsGroup, resp_1.json()['data']['id'])
    assert g11.uae == '11gt'
    assert g1.uae == '1gt'


async def test_org_dona_opera_o_proprio_grupo_e_tipo(
    client, session, admin_1gt_token, alien
):
    """Controle positivo: a '1gt' altera e remove o que é dela."""
    empty_id, group_id, type_id = alien
    headers = _auth(admin_1gt_token)

    resp = await client.put(
        f'{BASE}/groups/{group_id}', json={'short': 'ok'}, headers=headers
    )
    assert resp.status_code == HTTPStatus.OK
    resp = await client.put(
        f'{BASE}/types/{type_id}', json={'short': 'ok'}, headers=headers
    )
    assert resp.status_code == HTTPStatus.OK
    resp = await client.delete(f'{BASE}/groups/{empty_id}', headers=headers)
    assert resp.status_code == HTTPStatus.OK

    assert (await _fresh(session, QuadsGroup, group_id)).short == 'ok'
    assert (await _fresh(session, QuadsType, type_id)).short == 'ok'
    assert await _fresh(session, QuadsGroup, empty_id) is None


# ---------------------------------------------------------------------------
# Caminhos felizes: grupo
# ---------------------------------------------------------------------------


async def test_create_group(client, session, token):
    resp = await client.post(
        f'{BASE}/groups',
        json={'short': 'novo', 'long': 'grupo novo'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['short'] == 'novo'
    assert data['long'] == 'grupo novo'
    group = await _fresh(session, QuadsGroup, data['id'])
    assert (group.short, group.long, group.uae) == (
        'novo',
        'grupo novo',
        '11gt',
    )


async def test_create_group_corpo_invalido_422(client, token):
    resp = await client.post(
        f'{BASE}/groups',
        json={'short': '', 'long': 'sem sigla'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_group_so_campos_enviados(client, session, token, own):
    """Só `short`/`long` mudam; `uae` no corpo é ignorado."""
    group_id, _ = own

    resp = await client.put(
        f'{BASE}/groups/{group_id}',
        json={'long': 'nome novo', 'uae': '1gt'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert (data['short'], data['long']) == ('g11', 'nome novo')
    group = await _fresh(session, QuadsGroup, group_id)
    assert (group.short, group.long, group.uae) == (
        'g11',
        'nome novo',
        '11gt',
    )


async def test_delete_group_vazio(client, session, token):
    group = await _mk_group(session, '11gt')
    group_id = group.id

    resp = await client.delete(
        f'{BASE}/groups/{group_id}', headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert await _fresh(session, QuadsGroup, group_id) is None


# ---------------------------------------------------------------------------
# Caminhos felizes: tipo
# ---------------------------------------------------------------------------


async def test_create_type(client, session, token, own):
    group_id, _ = own

    resp = await client.post(
        f'{BASE}/groups/{group_id}/types',
        json={'short': 'novo', 'long': 'tipo novo'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['group_id'] == group_id
    assert (data['short'], data['long']) == ('novo', 'tipo novo')
    assert data['funcs_list'] == []
    type_db = await _fresh(session, QuadsType, data['id'])
    assert type_db.group_id == group_id
    assert await _funcs(session, data['id']) == []


async def test_update_type_so_campos_enviados_e_devolve_funcs(
    client, session, token, own, alien
):
    """Só `short`/`long` mudam; `group_id` no corpo é ignorado."""
    group_id, type_id = own
    _, group_1gt_id, _ = alien

    resp = await client.put(
        f'{BASE}/types/{type_id}',
        json={'long': 'nome novo', 'group_id': group_1gt_id},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert (data['short'], data['long']) == ('t11', 'nome novo')
    assert sorted(data['funcs_list']) == ['mc', 'pil']
    type_db = await _fresh(session, QuadsType, type_id)
    assert (type_db.short, type_db.long) == ('t11', 'nome novo')
    assert type_db.group_id == group_id
    assert await _funcs(session, type_id) == ['mc', 'pil']


async def test_delete_type_remove_tipo_e_funcoes(client, session, token, own):
    group_id, type_id = own

    resp = await client.delete(f'{BASE}/types/{type_id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert await _fresh(session, QuadsType, type_id) is None
    assert await _funcs(session, type_id) == []
    # O grupo não é afetado.
    assert await _fresh(session, QuadsGroup, group_id) is not None


# ---------------------------------------------------------------------------
# PUT /types/{id}/funcs
# ---------------------------------------------------------------------------


async def test_set_funcs_substitui_o_conjunto(client, session, token, own):
    _, type_id = own

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': ['oe', 'tf']},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['funcs_list'] == ['oe', 'tf']
    # pil e mc (antigas) somem.
    assert await _funcs(session, type_id) == ['oe', 'tf']


async def test_set_funcs_dedup_preserva_ordem_e_lowercase(
    client, session, token, own
):
    _, type_id = own

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': ['TF', 'pil', 'Tf', 'PIL', 'oe']},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['funcs_list'] == ['tf', 'pil', 'oe']
    assert await _funcs(session, type_id) == ['oe', 'pil', 'tf']


async def test_set_funcs_lista_vazia_limpa_tudo(client, session, token, own):
    _, type_id = own

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': []},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['funcs_list'] == []
    assert await _funcs(session, type_id) == []


# ---------------------------------------------------------------------------
# 409: dependências
# ---------------------------------------------------------------------------


async def test_delete_group_com_tipos_409(client, session, token, own):
    group_id, type_id = own

    resp = await client.delete(
        f'{BASE}/groups/{group_id}', headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.CONFLICT
    assert 'possui tipos' in resp.json()['message']
    assert await _fresh(session, QuadsGroup, group_id) is not None
    assert await _fresh(session, QuadsType, type_id) is not None


async def test_delete_type_com_quadrinho_409(
    client, session, token, own, trip
):
    _, type_id = own
    quad = QuadFactory(trip_id=trip.id, type_id=type_id)
    session.add(quad)
    await session.commit()
    quad_id = quad.id

    resp = await client.delete(f'{BASE}/types/{type_id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.CONFLICT
    assert 'quadrinhos registrados' in resp.json()['message']
    assert await _fresh(session, QuadsType, type_id) is not None
    assert await _funcs(session, type_id) == ['mc', 'pil']
    assert await _fresh(session, Quad, quad_id) is not None


# ---------------------------------------------------------------------------
# 400: função que a org não opera
# ---------------------------------------------------------------------------


@pytest.fixture
async def recorte_11gt(session):
    """A '11gt' deixa de operar `md` (a '1gt' segue operando) e desativa `ml`.

    As demais de `tests/seed/funcoes.py::CODIGOS` seguem operadas e ativas.
    """
    await session.execute(
        delete(FuncaoUae).where(
            FuncaoUae.uae == '11gt', FuncaoUae.func_cod == 'md'
        )
    )
    await session.execute(
        update(FuncaoUae)
        .where(FuncaoUae.uae == '11gt', FuncaoUae.func_cod == 'ml')
        .values(active=False)
    )
    await session.commit()


@pytest.mark.parametrize(
    'funcao',
    ['md', 'ml', 'zz'],
    ids=['operada-so-por-outra-org', 'inativa-na-org', 'fora-do-catalogo'],
)
async def test_set_funcs_nao_operada_400(
    client, session, token, own, recorte_11gt, funcao
):
    _, type_id = own

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': [funcao]},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert funcao in resp.json()['message']
    assert await _funcs(session, type_id) == ['mc', 'pil']


async def test_set_funcs_mistura_valida_e_invalida_nao_altera_nada(
    client, session, token, own, recorte_11gt
):
    _, type_id = own

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': ['oe', 'MD']},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'].endswith(': md')
    # `oe` (válida) não foi gravada e pil/mc (antigas) não foram apagadas.
    assert await _funcs(session, type_id) == ['mc', 'pil']


async def test_set_funcs_funcao_operada_pela_propria_org_passa(
    client, session, admin_1gt_token, alien, recorte_11gt
):
    """Controle: `md` é inválida para a '11gt' mas válida para a '1gt'."""
    _, _, type_id = alien

    resp = await client.put(
        f'{BASE}/types/{type_id}/funcs',
        json={'funcs': ['md']},
        headers=_auth(admin_1gt_token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert await _funcs(session, type_id) == ['md']
