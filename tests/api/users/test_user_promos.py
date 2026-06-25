"""
Testes para os endpoints de promoções de usuário:

- GET    /users/{user_id}/promocoes             (list_user_promos)
- POST   /users/{user_id}/promocoes             (create_user_promo)
- DELETE /users/{user_id}/promocoes/{promo_id}  (delete_user_promo)

A hierarquia de carreira é validada por validate_promo_hierarchy:
posto_grad.ant define a antiguidade (menor ant = graduação superior), e a
linha do tempo deve ser estritamente ascendente em graduação conforme a
data aumenta (ant deve diminuir).

Antiguidades usadas (do seed posto_grad): 3s=14, 2s=13, 1s=12.
"""

from datetime import date
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.shared.users import UserPromo

pytestmark = pytest.mark.anyio


async def _add_promo(session, user_id, p_g, data_promo):
    """Insere uma promoção diretamente no banco (setup de cenário)."""
    promo = UserPromo(user_id=user_id, p_g=p_g, data_promo=data_promo)
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


# --------------------------------------------------------------------------
# GET /users/{user_id}/promocoes
# --------------------------------------------------------------------------


async def test_list_promos_empty(client, users, token):
    """Usuário sem histórico (dono) recebe lista vazia."""
    user, _ = users

    response = await client.get(
        f'/users/{user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_list_promos_ordered_desc(client, session, users, token):
    """Promoções são retornadas da mais recente para a mais antiga."""
    user, _ = users
    await _add_promo(session, user.id, '3s', date(2018, 1, 1))
    await _add_promo(session, user.id, '2s', date(2020, 1, 1))
    await _add_promo(session, user.id, '1s', date(2022, 1, 1))

    response = await client.get(
        f'/users/{user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert [p['data_promo'] for p in data] == [
        '2022-01-01',
        '2020-01-01',
        '2018-01-01',
    ]
    assert data[0]['p_g'] == '1s'
    assert data[0]['posto']['short'] == '1s'
    assert data[0]['user_id'] == user.id


async def test_list_promos_with_view_permission(
    client, session, users, user_with_view_permission, make_token
):
    """Quem tem user:view enxerga o histórico de outro usuário."""
    _, other_user = users
    await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))
    token = await make_token(user_with_view_permission)

    response = await client.get(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(response.json()['data']) == 1


async def test_list_promos_other_user_without_permission_forbidden(
    client, users, make_token
):
    """Sem ownership nem user:view, listar o histórico alheio dá 403."""
    user, other_user = users
    token = await make_token(user, ensure_role=False)

    response = await client.get(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_list_promos_user_not_found(client, token):
    """Listar promoções de usuário inexistente retorna 404."""
    response = await client.get(
        '/users/99999999/promocoes',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_list_promos_without_token(client, users):
    """Requisição sem token é rejeitada."""
    user, _ = users
    response = await client.get(f'/users/{user.id}/promocoes')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# --------------------------------------------------------------------------
# POST /users/{user_id}/promocoes
# --------------------------------------------------------------------------


async def test_create_promo_success(
    client, session, users, user_with_update_permission, make_token
):
    """Com user:update, cria promoção em histórico vazio."""
    _, other_user = users
    token = await make_token(user_with_update_permission)

    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '2s', 'data_promo': '2022-01-01'},
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['p_g'] == '2s'
    assert data['data_promo'] == '2022-01-01'
    assert data['user_id'] == other_user.id
    assert data['posto']['short'] == '2s'

    db_promo = await session.scalar(
        select(UserPromo).where(UserPromo.user_id == other_user.id)
    )
    assert db_promo is not None
    assert db_promo.p_g == '2s'


async def test_create_promo_valid_chain(
    client, users, user_with_update_permission, make_token
):
    """Sequência de graduações ascendentes ao longo do tempo é aceita."""
    _, other_user = users
    token = await make_token(user_with_update_permission)
    base = f'/users/{other_user.id}/promocoes'
    headers = {'Authorization': f'Bearer {token}'}

    for p_g, data_promo in (
        ('3s', '2018-01-01'),
        ('2s', '2020-01-01'),
        ('1s', '2022-01-01'),
    ):
        response = await client.post(
            base, headers=headers, json={'p_g': p_g, 'data_promo': data_promo}
        )
        assert response.status_code == HTTPStatus.CREATED


async def test_create_promo_user_not_found(
    client, user_with_update_permission, make_token
):
    """Criar promoção para usuário inexistente retorna 404."""
    token = await make_token(user_with_update_permission)

    response = await client.post(
        '/users/99999999/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '2s', 'data_promo': '2022-01-01'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_create_promo_without_permission(client, users, make_token):
    """Sem user:update, criar promoção dá 403."""
    user, other_user = users
    token = await make_token(user, ensure_role=False)

    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '2s', 'data_promo': '2022-01-01'},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_create_promo_without_token(client, users):
    """Requisição sem token é rejeitada."""
    _, other_user = users
    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        json={'p_g': '2s', 'data_promo': '2022-01-01'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_promo_duplicate_grade_fails(
    client, session, users, user_with_update_permission, make_token
):
    """Graduação já presente no histórico é rejeitada."""
    _, other_user = users
    await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))
    token = await make_token(user_with_update_permission)

    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '2s', 'data_promo': '2023-01-01'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'histórico' in response.json()['message'].lower()


async def test_create_promo_duplicate_date_fails(
    client, session, users, user_with_update_permission, make_token
):
    """Data já utilizada por outra promoção é rejeitada."""
    _, other_user = users
    await _add_promo(session, other_user.id, '3s', date(2020, 1, 1))
    token = await make_token(user_with_update_permission)

    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '2s', 'data_promo': '2020-01-01'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'data' in response.json()['message'].lower()


async def test_create_promo_violates_previous_fails(
    client, session, users, user_with_update_permission, make_token
):
    """Graduação inferior à promoção anterior na linha do tempo é rejeitada."""
    _, other_user = users
    # Anterior: 2s (ant 13) em 2020. Nova: 3s (ant 14) em 2022 -> rebaixa.
    await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))
    token = await make_token(user_with_update_permission)

    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '3s', 'data_promo': '2022-01-01'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'anterior' in response.json()['message'].lower()


async def test_create_promo_violates_next_fails(
    client, session, users, user_with_update_permission, make_token
):
    """Graduação superior à promoção posterior na linha do tempo é vetada."""
    _, other_user = users
    # Posterior: 3s (ant 14) em 2024. Nova: 2s (ant 13) em 2022 -> supera.
    await _add_promo(session, other_user.id, '3s', date(2024, 1, 1))
    token = await make_token(user_with_update_permission)

    response = await client.post(
        f'/users/{other_user.id}/promocoes',
        headers={'Authorization': f'Bearer {token}'},
        json={'p_g': '2s', 'data_promo': '2022-01-01'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'posterior' in response.json()['message'].lower()


# --------------------------------------------------------------------------
# DELETE /users/{user_id}/promocoes/{promo_id}
# --------------------------------------------------------------------------


async def test_delete_promo_success(
    client, session, users, user_with_update_permission, make_token
):
    """Com user:update, remove a promoção e ela some do banco."""
    _, other_user = users
    promo = await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))
    token = await make_token(user_with_update_permission)

    response = await client.delete(
        f'/users/{other_user.id}/promocoes/{promo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['status'] == 'success'

    db_promo = await session.scalar(
        select(UserPromo).where(UserPromo.id == promo.id)
    )
    assert db_promo is None


async def test_delete_promo_not_found(
    client, users, user_with_update_permission, make_token
):
    """Remover promoção inexistente retorna 404."""
    _, other_user = users
    token = await make_token(user_with_update_permission)

    response = await client.delete(
        f'/users/{other_user.id}/promocoes/99999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_delete_promo_wrong_user_returns_not_found(
    client, session, users, user_with_update_permission, make_token
):
    """promo_id existe mas pertence a outro usuário -> 404 (filtro user+id)."""
    user, other_user = users
    promo = await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))
    token = await make_token(user_with_update_permission)

    response = await client.delete(
        f'/users/{user.id}/promocoes/{promo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_delete_promo_without_permission(
    client, session, users, make_token
):
    """Sem user:update, remover promoção dá 403."""
    user, other_user = users
    promo = await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))
    token = await make_token(user, ensure_role=False)

    response = await client.delete(
        f'/users/{other_user.id}/promocoes/{promo.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_delete_promo_without_token(client, session, users):
    """Requisição sem token é rejeitada."""
    _, other_user = users
    promo = await _add_promo(session, other_user.id, '2s', date(2020, 1, 1))

    response = await client.delete(
        f'/users/{other_user.id}/promocoes/{promo.id}',
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
