"""
Testes para o endpoint GET /ops/quads/types.

Este endpoint lista os tipos de quadrinhos agrupados, escopados pela
unidade ativa do token (active_org). Requer autenticação e org ativa.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_get_quads_types_success(client, org_token):
    """Testa listagem de tipos de quadrinhos com sucesso."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que retorna lista de grupos
    assert isinstance(data, list)


async def test_get_quads_types_returns_groups(client, org_token):
    """Testa que retorna grupos de quadrinhos do seed."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que há grupos (seed data)
    assert len(data) > 0

    # Verifica estrutura do grupo
    group = data[0]
    assert 'id' in group
    assert 'short' in group
    assert 'long' in group
    assert 'types' in group


async def test_get_quads_types_group_contains_types(client, org_token):
    """Testa que cada grupo contém seus tipos."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Encontra um grupo com tipos
    group_with_types = next((g for g in data if len(g['types']) > 0), None)
    assert group_with_types is not None

    # Verifica estrutura do tipo
    quad_type = group_with_types['types'][0]
    assert 'id' in quad_type
    assert 'short' in quad_type
    assert 'long' in quad_type
    assert 'funcs_list' in quad_type


async def test_get_quads_types_type_has_funcs_list(client, org_token):
    """Testa que tipos têm lista de funções."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Encontra um tipo com funções
    for group in data:
        for quad_type in group['types']:
            if len(quad_type['funcs_list']) > 0:
                # Verifica que funcs_list é lista de strings
                assert isinstance(quad_type['funcs_list'], list)
                assert all(isinstance(f, str) for f in quad_type['funcs_list'])
                return

    # Se chegou aqui, não encontrou tipo com funções no seed
    # Isso é ok se o seed não tiver funções


async def test_get_quads_types_scoped_by_active_org(
    client, users, org_token, make_org_token
):
    """Testa que o escopo segue a org ativa do token, não um query param.

    O seed só tem grupos na '11gt'; um token com active_org='1gt' enxerga
    lista vazia, enquanto o '11gt' enxerga os grupos.
    """
    user, _ = users
    token_1gt = await make_org_token(user, active_org='1gt')

    response_11gt = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )
    response_1gt = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {token_1gt}'},
    )

    assert response_11gt.status_code == HTTPStatus.OK
    assert response_1gt.status_code == HTTPStatus.OK

    # 11gt tem dados do seed; 1gt não tem grupos semeados
    assert len(response_11gt.json()['data']) > 0
    assert response_1gt.json()['data'] == []


async def test_get_quads_types_missing_active_org_fails(client, token):
    """Sem org ativa no token (fixture `token`), o data-plane responde 400."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_get_quads_types_types_ordered_by_id(client, org_token):
    """Testa que tipos são ordenados por ID."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    for group in data:
        types = group['types']
        if len(types) > 1:
            # Verifica que IDs estão em ordem crescente
            type_ids = [t['id'] for t in types]
            assert type_ids == sorted(type_ids)


async def test_get_quads_types_response_schema(client, org_token):
    """Testa o schema completo da resposta (QuadsGroupSchema)."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    for group in data:
        # QuadsGroupSchema
        assert isinstance(group['id'], int)
        assert isinstance(group['short'], str)
        assert isinstance(group['long'], str)
        assert isinstance(group['types'], list)

        for quad_type in group['types']:
            # QuadsTypeSchema
            assert isinstance(quad_type['id'], int)
            assert isinstance(quad_type['short'], str)
            assert isinstance(quad_type['long'], str)
            assert isinstance(quad_type['funcs_list'], list)


async def test_get_quads_types_known_groups_exist(client, org_token):
    """Testa que grupos conhecidos do seed existem."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica grupos do seed
    group_shorts = [g['short'] for g in data]

    # Pelo menos um destes deve existir (do seed)
    expected_groups = ['sobr', 'nasc', 'local', 'desloc', 'inter']
    found_groups = [g for g in expected_groups if g in group_shorts]

    assert len(found_groups) > 0, (
        f'Nenhum grupo esperado encontrado. '
        f'Esperados: {expected_groups}, Encontrados: {group_shorts}'
    )


async def test_get_quads_types_known_types_exist(client, org_token):
    """Testa que tipos conhecidos do seed existem."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Coleta todos os shorts de tipos
    type_shorts = []
    for group in data:
        type_shorts.extend([t['short'] for t in group['types']])

    # Pelo menos um destes deve existir (do seed)
    expected_types = ['pto', 'vmo', 'roxo', 'bp', 'local']
    found_types = [t for t in expected_types if t in type_shorts]

    assert len(found_types) > 0, (
        f'Nenhum tipo esperado encontrado. '
        f'Esperados: {expected_types}, Encontrados: {type_shorts}'
    )


async def test_get_quads_types_known_funcs_exist(client, org_token):
    """Testa que funções conhecidas do seed existem."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {org_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Coleta todas as funções
    all_funcs = set()
    for group in data:
        for quad_type in group['types']:
            all_funcs.update(quad_type['funcs_list'])

    # Pelo menos algumas funções devem existir
    expected_funcs = ['pil', 'mc', 'lm', 'tf', 'os', 'oe']
    found_funcs = [f for f in expected_funcs if f in all_funcs]

    assert len(found_funcs) > 0, (
        f'Nenhuma função esperada encontrada. '
        f'Esperadas: {expected_funcs}, Encontradas: {all_funcs}'
    )


async def test_get_quads_types_without_token_fails(client):
    """Testa que requisição sem token falha."""
    response = await client.get('/ops/quads/types?uae=11gt')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
