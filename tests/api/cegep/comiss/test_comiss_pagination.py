"""Ordenação global, histórico paginado e leitura completa do portal."""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import ComissFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/comiss/'


async def test_fechados_paginas_sem_perder_empates(
    client, session, token, users
):
    user, _ = users
    registros = [
        ComissFactory(user_id=user.id, status='fechado') for _ in range(25)
    ]
    session.add_all(registros)
    await session.commit()
    ids = []
    for page, tamanho in [(1, 20), (2, 5)]:
        response = await client.get(
            URL,
            params={
                'status': 'fechado',
                'page': page,
                'order_by': 'data_ab',
                'direction': 'asc',
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert body['total'] == 25
        assert body['pages'] == 2
        assert body['page'] == page
        assert body['per_page'] == 20
        assert len(body['data']) == tamanho
        ids.extend(item['id'] for item in body['data'])
    assert ids == [registro.id for registro in registros]


async def test_abertos_completos_mesmo_com_parametros_de_pagina(
    client, session, token, users
):
    user, _ = users
    registros = [ComissFactory(user_id=user.id) for _ in range(25)]
    session.add_all(registros)
    await session.commit()
    response = await client.get(
        URL,
        params={'status': 'aberto', 'page': 2, 'per_page': 5},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()['data']) == 25


async def test_fechados_aceita_teto_de_pagina(client, session, token, users):
    user, _ = users
    session.add(ComissFactory(user_id=user.id, status='fechado'))
    await session.commit()
    response = await client.get(
        URL,
        params={'status': 'fechado', 'page': 10_000},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    # Página além do total volta vazia com metadados para o Client se ajustar.
    assert body['data'] == []
    assert body['page'] == 10_000
    assert body['pages'] == 1
    assert body['total'] == 1


async def test_total_filtrado_preserva_escopo(client, session, token, users):
    user, other = users
    registros = [
        ComissFactory(user_id=user.id, status='fechado') for _ in range(3)
    ]
    session.add_all([
        *registros,
        ComissFactory(user_id=user.id, status='fechado', uae='1gt'),
        ComissFactory(user_id=user.id, status='aberto'),
        ComissFactory(user_id=other.id, status='fechado'),
    ])
    await session.commit()
    response = await client.get(
        URL,
        params={
            'status': 'fechado',
            'user_id': user.id,
            'page': 2,
            'per_page': 2,
            'order_by': 'data_ab',
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body['total'] == 3
    assert body['pages'] == 2
    assert [item['id'] for item in body['data']] == [registros[2].id]


@pytest.mark.parametrize('status', ['aberto', 'fechado'])
@pytest.mark.parametrize('direction', ['asc', 'desc'])
@pytest.mark.parametrize(
    ('order_by', 'indices'),
    [
        ('data_ab', [2, 1, 0]),
        ('data_fc', [1, 0, 2]),
        ('tipo', [0, 2, 1]),
        ('completude', [2, 0, 1]),
        ('modulo', [0, 2, 1]),
        ('previsto', [2, 1, 0]),
        ('computado', [2, 0, 1]),
        ('restante', [1, 2, 0]),
    ],
)
async def test_ordem_global_colunas(
    client, session, token, users, status, direction, order_by, indices
):
    user, _ = users
    today = date(2026, 1, 1)
    registros = [
        ComissFactory(
            user_id=user.id,
            status=status,
            data_ab=today + timedelta(days=2 - i),
            data_fc=today + timedelta(days=[20, 10, 30][i]),
            dias_cumprir=[None, 8, None][i],
            valor_aj_ab=[3350, 10000, 1675][i],
            valor_aj_fc=0,
        )
        for i in range(3)
    ]
    session.add_all(registros)
    await session.flush()
    for registro, cache in zip(
        registros,
        [
            {'dias_comp': 50, 'vals_comp': 670, 'completude': 30},
            {'dias_comp': 7, 'vals_comp': 0, 'completude': 80, 'modulo': True},
            {},
        ],
        strict=True,
    ):
        registro.cache_calc = cache
    await session.commit()
    # Empates mantêm ID crescente, inclusive em direção descendente.
    if direction == 'desc':
        indices = {
            'tipo': [1, 0, 2],
            'modulo': [1, 0, 2],
        }.get(order_by, list(reversed(indices)))
    ids = []
    for page in range(1, 4) if status == 'fechado' else [1]:
        response = await client.get(
            URL,
            params={
                'status': status,
                'order_by': order_by,
                'direction': direction,
                'page': page,
                'per_page': 1,
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.OK
        ids.extend(item['id'] for item in response.json()['data'])
    assert ids == [registros[i].id for i in indices]


@pytest.mark.parametrize('direction', ['asc', 'desc'])
async def test_antiguidade_nulos_e_desempate(
    client, session, token, users, direction
):
    user, other = users
    user.p_g = other.p_g = '3s'
    user.ult_promo = None
    other.ult_promo = date(2020, 1, 1)
    user.ant_rel = None
    registros = [
        ComissFactory(user_id=other.id),
        ComissFactory(user_id=user.id),
        ComissFactory(user_id=user.id),
    ]
    session.add_all(registros)
    await session.commit()
    response = await client.get(
        URL,
        params={
            'status': 'aberto',
            'order_by': 'militar',
            'direction': direction,
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    indices = [1, 2, 0] if direction == 'asc' else [0, 1, 2]
    assert [item['id'] for item in response.json()['data']] == [
        registros[i].id for i in indices
    ]


@pytest.mark.parametrize('status', ['aberto', 'fechado'])
@pytest.mark.parametrize('direction', ['asc', 'desc'])
@pytest.mark.parametrize('criterio', ['posto', 'ant_rel'])
async def test_antiguidade_posto_e_relativa(
    client, session, token, users, status, direction, criterio
):
    user, other = users
    user.p_g = 'cp' if criterio == 'posto' else '3s'
    other.p_g = '3s'
    user.ult_promo = date(2025, 1, 1)
    other.ult_promo = (
        date(2010, 1, 1) if criterio == 'posto' else user.ult_promo
    )
    user.ant_rel = None
    other.ant_rel = 1
    antigo = ComissFactory(user_id=user.id, status=status)
    moderno = ComissFactory(user_id=other.id, status=status)
    session.add_all([moderno, antigo])
    await session.commit()
    ids = []
    for page in [1, 2] if status == 'fechado' else [1]:
        response = await client.get(
            URL,
            params={
                'status': status,
                'order_by': 'militar',
                'direction': direction,
                'page': page,
                'per_page': 1,
            },
            headers={'Authorization': f'Bearer {token}'},
        )
        assert response.status_code == HTTPStatus.OK
        ids.extend(item['id'] for item in response.json()['data'])
    esperado = [antigo.id, moderno.id]
    assert ids == (esperado if direction == 'asc' else esperado[::-1])


@pytest.mark.parametrize('com_user_id', [True, False])
async def test_ordem_legada_sem_order_by(
    client, session, token, users, com_user_id
):
    user, other = users
    registros = [
        ComissFactory(user_id=user.id, data_ab=date(2026, 1, 10)),
        ComissFactory(
            user_id=other.id, status='fechado', data_ab=date(2026, 3, 1)
        ),
        ComissFactory(
            user_id=user.id, status='fechado', data_ab=date(2026, 1, 10)
        ),
        ComissFactory(user_id=user.id, data_ab=date(2026, 2, 1)),
    ]
    session.add_all(registros)
    await session.commit()
    params = {'user_id': user.id} if com_user_id else {}
    response = await client.get(
        URL, params=params, headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == HTTPStatus.OK
    # data_ab DESC; empate na mesma data_ab desempata por ID crescente.
    indices = [3, 0, 2] if com_user_id else [1, 3, 0, 2]
    assert [item['id'] for item in response.json()['data']] == [
        registros[i].id for i in indices
    ]


@pytest.mark.parametrize('direction', ['asc', 'desc'])
async def test_antiguidade_ult_promo_antes_de_ant_rel(
    client, session, token, users, direction
):
    user, other = users
    user.p_g = other.p_g = '3s'
    user.ult_promo = date(2015, 1, 1)
    other.ult_promo = date(2020, 1, 1)
    # Relativa invertida: se decidisse antes da promoção, a ordem trocaria.
    user.ant_rel = 5
    other.ant_rel = 1
    antigo = ComissFactory(user_id=user.id)
    moderno = ComissFactory(user_id=other.id)
    session.add_all([moderno, antigo])
    await session.commit()
    response = await client.get(
        URL,
        params={
            'status': 'aberto',
            'order_by': 'militar',
            'direction': direction,
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK
    esperado = [antigo.id, moderno.id]
    assert [item['id'] for item in response.json()['data']] == (
        esperado if direction == 'asc' else esperado[::-1]
    )


async def test_portal_historico_completo_sem_permissao(
    client, session, token_sem_perm, users
):
    user, other = users
    registros = [
        ComissFactory(user_id=user.id, status='fechado') for _ in range(25)
    ]
    session.add_all([*registros, ComissFactory(user_id=other.id)])
    await session.commit()
    response = await client.get(
        URL,
        params={'user_id': user.id},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )
    assert response.status_code == HTTPStatus.OK
    assert len(response.json()['data']) == 25
    user_ids = {item['user']['id'] for item in response.json()['data']}
    assert user_ids == {user.id}


@pytest.mark.parametrize(
    'params',
    [
        {'page': 0},
        {'page': -1},
        {'page': 10_001},
        {'per_page': 0},
        {'per_page': 101},
        {'order_by': 'invalido'},
        {'direction': 'invalida'},
    ],
)
async def test_parametros_invalidos(client, token, params):
    response = await client.get(
        URL,
        params={'status': 'fechado', **params},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
