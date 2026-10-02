from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.users import User
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def matching_trips(session):
    specs = [
        ('3s', 2018, 2, True, True, '11gt'),
        ('2s', 2020, 2, False, False, '11gt'),
        ('2s', 2018, 2, True, True, '11gt'),
        ('2s', 2018, 1, True, True, '11gt'),
        ('cb', 2010, 1, False, True, '11gt'),
        ('2s', 2010, 1, True, True, '1gt'),
    ]
    trips = []
    for pg, year, ant, active, user_active, org in specs:
        user = UserFactory(
            p_g=pg,
            nome_guerra='Águia',
            nome_completo='Busca Águia da Silva',
            ult_promo=date(year, 1, 1),
            ant_rel=ant,
        )
        user.active = user_active
        session.add(user)
        await session.flush()
        trip = TripFactory(
            user_id=user.id,
            active=active,
            uae=org,
            proj='c-130' if org == '1gt' else 'kc-390',
        )
        session.add(trip)
        await session.flush()
        trips.append(trip)
    await session.commit()
    return trips


async def test_search_includes_inactive_and_orders_groups_before_pagination(
    client, token, matching_trips
):
    expected = [matching_trips[i].id for i in (3, 2, 0, 1, 4)]
    found = []
    for page in (1, 2, 3):
        response = await client.get(
            '/ops/trips/',
            params={
                'search': 'aguia',
                'page': page,
                'per_page': 2,
                'include_inactive': True,
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body['total'] == 5
        assert body['pages'] == 3
        found.extend(item['id'] for item in body['data'])
    assert found == expected


async def test_search_matches_trigram(client, token, matching_trips):
    trip = matching_trips[1]
    response = await client.get(
        '/ops/trips/',
        params={'search': trip.trig.lower(), 'include_inactive': True},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert [item['id'] for item in response.json()['data']] == [trip.id]


async def test_existing_search_keeps_active_only_default(
    client, token, matching_trips
):
    response = await client.get(
        '/ops/trips/',
        params={'search': 'aguia'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert [item['id'] for item in response.json()['data']] == [
        matching_trips[i].id for i in (3, 2, 0)
    ]


async def test_missing_seniority_keeps_canonical_order_across_pages(
    client, session, token, matching_trips
):
    for index in (2, 3):
        user = await session.get(User, matching_trips[index].user_id)
        user.ult_promo = None
        user.ant_rel = None if index == 3 else 2
    user = await session.get(User, matching_trips[0].user_id)
    user.p_g = '2s'
    await session.commit()
    ids = []
    for page in (1, 2, 3):
        response = await client.get(
            '/ops/trips/',
            params={
                'search': 'aguia',
                'include_inactive': True,
                'per_page': 1,
                'page': page,
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.OK
        ids.extend(item['id'] for item in response.json()['data'])
    assert ids == [matching_trips[i].id for i in (3, 2, 0)]


async def test_search_requires_permission(client, token_sem_perm):
    response = await client.get(
        '/ops/trips/',
        params={'search': 'silva', 'include_inactive': True},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    'params',
    [
        {'search': 'silva', 'page': 0},
        {'search': 'silva', 'per_page': 0},
        {'search': 'silva', 'per_page': 101},
    ],
)
async def test_search_validates_query(client, token, params):
    response = await client.get(
        '/ops/trips/',
        params={**params, 'include_inactive': True},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_vinculo_ativo_de_usuario_inativo_segue_os_inativos(
    client, session, token, matching_trips
):
    user = UserFactory(
        p_g='3s',
        nome_guerra='Águia',
        nome_completo='Busca Águia da Silva',
        ult_promo=date(2018, 1, 1),
        ant_rel=2,
    )
    user.active = False
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, active=True, uae='11gt', proj='kc-390')
    session.add(trip)
    await session.commit()

    found = []
    for page in (1, 2, 3):
        response = await client.get(
            '/ops/trips/',
            params={
                'search': 'aguia',
                'page': page,
                'per_page': 2,
                'include_inactive': True,
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body['total'] == 6
        found.extend(item['id'] for item in body['data'])

    ativos = [matching_trips[i].id for i in (3, 2, 0)]
    assert found[:3] == ativos
    assert trip.id in found[3:]
    assert set(found[3:]) == {
        matching_trips[1].id,
        matching_trips[4].id,
        trip.id,
    }

    response = await client.get(
        '/ops/trips/',
        params={'search': 'aguia'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert [item['id'] for item in response.json()['data']] == ativos
