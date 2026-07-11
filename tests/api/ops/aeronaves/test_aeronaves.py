"""
Testes para os endpoints CRUD de Aeronaves (/ops/aeronaves/).

O escopo é multi-tenant: a org só enxerga/cadastra a frota dos projetos
que opera (via `tenant_projetos`). Nos testes, '11gt' opera o kc-390 (C8)
e '1gt' opera o c-130 (C1). As rotas de escrita exigem permissão na org
ativa (token); as de leitura bastam org ativa (token_sem_perm).
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.aeronaves import Aeronave

pytestmark = pytest.mark.anyio


# ========================================
# POST /ops/aeronaves/ (Create)
# ========================================


async def test_create_aeronave_success(client, token):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2860',
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['matricula'] == '2860'
    assert data['data']['active'] is True
    assert data['data']['sit'] == 'DI'
    assert data['data']['projeto'] == 'C8'
    assert data['data']['proj']['modelo'] == 'kc-390'


async def test_create_aeronave_with_obs(client, token):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2861',
            'active': True,
            'sit': 'DO',
            'obs': 'Restrição no radar',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data['data']['obs'] == 'Restrição no radar'


async def test_create_aeronave_projeto_not_in_org_fails(client, token):
    """Projeto não operado pela org ativa não pode ser cadastrado (400).

    O token é de '11gt' (opera C8); C1 pertence a '1gt'.
    """
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2862',
            'active': True,
            'sit': 'DI',
            'projeto': 'C1',
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data['message'] == 'Projeto não disponível para a organização'


async def test_create_aeronave_duplicate_matricula_fails(
    client, token, aeronave
):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': aeronave.matricula,
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_create_aeronave_invalid_sit_fails(client, token):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '2870',
            'active': True,
            'sit': 'X',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_aeronave_matricula_not_4_digits_fails(client, token):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': '123',
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_aeronave_matricula_non_numeric_fails(client, token):
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'matricula': 'ABCD',
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_aeronave_without_permission_fails(
    client, token_sem_perm
):
    """Org ativa sem permissão de escrita não cadastra aeronave (403).

    `token_sem_perm` tem vínculo admin de Sistema (org None), que não satisfaz
    o escopo da org ativa '11gt' no permission_checker.
    """
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
        json={
            'matricula': '2865',
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_create_aeronave_missing_active_org_fails(client, token_sistema):
    """Sem org ativa no token_sistema, criar aeronave responde 400."""
    response = await client.post(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json={
            'matricula': '2880',
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_create_aeronave_without_auth_fails(client):
    response = await client.post(
        '/ops/aeronaves/',
        json={
            'matricula': '2880',
            'active': True,
            'sit': 'DI',
            'projeto': 'C8',
        },
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ========================================
# GET /ops/aeronaves/ (List)
# ========================================


async def test_list_aeronaves_success(client, token_sem_perm, aeronaves):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['total'] == 3
    assert len(data['data']) == 3


async def test_list_aeronaves_filter_by_sit(client, token_sem_perm, aeronaves):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
        params={'sit': 'DI'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['total'] == 1
    assert data['data'][0]['sit'] == 'DI'


async def test_list_aeronaves_filter_by_active(
    client, token_sem_perm, aeronaves
):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
        params={'active': 'true'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['total'] == 2
    assert all(a['active'] for a in data['data'])


async def test_list_aeronaves_empty(client, token_sem_perm):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['total'] == 0
    assert data['data'] == []


async def test_list_aeronaves_scoped_by_active_org(
    client, session, token_sem_perm, aeronaves
):
    """A frota de outro projeto/org não aparece na listagem da org ativa."""
    # Aeronave do projeto C1 (operado por '1gt', não por '11gt')
    outra = Aeronave(
        matricula='5000',
        active=True,
        sit='DI',
        obs=None,
        projeto='C1',
    )
    session.add(outra)
    await session.commit()

    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Só as 3 aeronaves C8 da org ativa; a C1 fica de fora
    assert data['total'] == 3
    matriculas = {a['matricula'] for a in data['data']}
    assert '5000' not in matriculas


async def test_list_aeronaves_missing_active_org_fails(client, token_sistema):
    response = await client.get(
        '/ops/aeronaves/',
        headers={'Authorization': f'Bearer {token_sistema}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


# ========================================
# GET /ops/aeronaves/projetos (Projetos da org)
# ========================================


async def test_list_org_projetos_success(client, token_sem_perm):
    response = await client.get(
        '/ops/aeronaves/projetos',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['data'] == [{'id_projeto': 'C8', 'modelo': 'kc-390'}]


# ========================================
# GET /ops/aeronaves/{matricula} (Detail)
# ========================================


async def test_get_aeronave_success(client, token_sem_perm, aeronave):
    response = await client.get(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['matricula'] == aeronave.matricula


async def test_get_aeronave_not_found(client, token_sem_perm):
    response = await client.get(
        '/ops/aeronaves/9999',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_get_aeronave_other_org_not_found(
    client, session, token_sem_perm
):
    """Aeronave de projeto de outra org é invisível (404)."""
    outra = Aeronave(
        matricula='5001',
        active=True,
        sit='DI',
        obs=None,
        projeto='C1',
    )
    session.add(outra)
    await session.commit()

    response = await client.get(
        '/ops/aeronaves/5001',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


# ========================================
# PUT /ops/aeronaves/{matricula} (Update)
# ========================================


async def test_update_aeronave_success(client, token, aeronave):
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token}'},
        json={'sit': 'IS', 'obs': 'Entrou em inspeção'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['status'] == 'success'
    assert data['data']['sit'] == 'IS'
    assert data['data']['obs'] == 'Entrou em inspeção'


async def test_update_aeronave_partial(client, token, aeronave):
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token}'},
        json={'active': False},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data['data']['active'] is False
    assert data['data']['sit'] == 'DI'


async def test_update_aeronave_projeto_not_in_org_fails(
    client, token, aeronave
):
    """Trocar para um projeto fora da org ativa falha (400)."""
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token}'},
        json={'projeto': 'C1'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data['message'] == 'Projeto não disponível para a organização'


async def test_update_aeronave_without_permission_fails(
    client, token_sem_perm, aeronave
):
    """Org ativa sem permissão de escrita não edita aeronave (403)."""
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token_sem_perm}'},
        json={'sit': 'IS'},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_update_aeronave_not_found(client, token):
    response = await client.put(
        '/ops/aeronaves/9999',
        headers={'Authorization': f'Bearer {token}'},
        json={'sit': 'DI'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_aeronave_other_org_not_found(client, session, token):
    """Atualizar aeronave de projeto de outra org responde 404."""
    outra = Aeronave(
        matricula='5002',
        active=True,
        sit='DI',
        obs=None,
        projeto='C1',
    )
    session.add(outra)
    await session.commit()

    response = await client.put(
        '/ops/aeronaves/5002',
        headers={'Authorization': f'Bearer {token}'},
        json={'sit': 'IS'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_aeronave_missing_active_org_fails(
    client, token_sistema, aeronave
):
    response = await client.put(
        f'/ops/aeronaves/{aeronave.matricula}',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json={'sit': 'IS'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
