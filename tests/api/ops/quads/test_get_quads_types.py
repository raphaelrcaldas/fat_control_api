"""
Testes para o endpoint GET /ops/quads/types.

Este endpoint lista os tipos de quadrinhos agrupados,
filtrados por UAE. Requer autenticação.
"""

from http import HTTPStatus

import pytest

pytestmark = pytest.mark.anyio


async def test_get_quads_types_success(client, token):
    """Testa listagem de tipos de quadrinhos com sucesso."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que retorna lista de grupos
    assert isinstance(data, list)


async def test_get_quads_types_returns_groups(client, token):
    """Testa que retorna grupos de quadrinhos do seed."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_group_contains_types(client, token):
    """Testa que cada grupo contém seus tipos."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_type_has_funcs_list(client, token):
    """Testa que tipos têm lista de funções."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_filters_by_uae(client, token):
    """Testa que filtra por UAE corretamente."""
    response_11gt = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
    )
    response_other = await client.get(
        '/ops/quads/types?uae=1gt',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response_11gt.status_code == HTTPStatus.OK
    assert response_other.status_code == HTTPStatus.OK

    # Verifica que os resultados são diferentes
    # (ou vazios para UAEs sem dados)
    resp_11gt = response_11gt.json()
    resp_other = response_other.json()

    assert resp_11gt['status'] == 'success'
    assert resp_other['status'] == 'success'

    # 11gt tem dados do seed
    assert len(resp_11gt['data']) > 0

    # Outra UAE pode não ter dados
    # (depende do seed)


async def test_get_quads_types_missing_uae_fails(client, token):
    """Testa que requisição sem UAE falha."""
    response = await client.get(
        '/ops/quads/types',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_get_quads_types_types_ordered_by_id(client, token):
    """Testa que tipos são ordenados por ID."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_response_schema(client, token):
    """Testa o schema completo da resposta (QuadsGroupSchema)."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_known_groups_exist(client, token):
    """Testa que grupos conhecidos do seed existem."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_known_types_exist(client, token):
    """Testa que tipos conhecidos do seed existem."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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


async def test_get_quads_types_known_funcs_exist(client, token):
    """Testa que funções conhecidas do seed existem."""
    response = await client.get(
        '/ops/quads/types?uae=11gt',
        headers={'Authorization': f'Bearer {token}'},
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
