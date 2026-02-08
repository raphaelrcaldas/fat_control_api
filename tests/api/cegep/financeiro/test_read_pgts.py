"""
Testes para o endpoint GET /cegep/financeiro/pgts.

Endpoint:
- GET /cegep/financeiro/pgts - Listar pagamentos

Cenarios de teste:
- Listagem vazia e com dados
- Filtros por tipo_doc, n_doc, sit, user, user_id, tipo
- Filtro por intervalo de datas (ini, fim)
- Paginacao
- Calculo de custos (custo_missao)
- Requisicao sem token

Requer autenticacao.
"""

from datetime import datetime, timedelta
from http import HTTPStatus

import pytest

from tests.factories import FragMisFactory, UserFragFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/financeiro/pgts'


# ============================================================
# Helpers
# ============================================================


def auth_header(token):
    return {'Authorization': f'Bearer {token}'}


async def create_missao_with_user(
    session,
    user,
    *,
    tipo_doc='om',
    n_doc=100,
    tipo='adm',
    sit='c',
    afast=None,
    regres=None,
    custos=None,
):
    """Cria uma missao com usuario vinculado."""
    now = datetime.now()
    afast = afast or now - timedelta(days=5)
    regres = regres or now - timedelta(days=2)

    missao = FragMisFactory(
        tipo_doc=tipo_doc,
        n_doc=n_doc,
        tipo=tipo,
        afast=afast,
        regres=regres,
        indenizavel=True,
        acrec_desloc=False,
    )
    session.add(missao)
    await session.commit()
    await session.refresh(missao)

    if custos is not None:
        missao.custos = custos
        session.add(missao)
        await session.commit()
        await session.refresh(missao)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit=sit,
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()

    return missao, user_frag


# ============================================================
# Listagem basica
# ============================================================


async def test_list_pgts_empty(client, token):
    """Testa listagem vazia quando nao ha pagamentos."""
    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []
    assert resp['total'] == 0


async def test_list_pgts_success(client, session, token, users):
    """Testa listagem com dados retornados."""
    user, _ = users

    await create_missao_with_user(session, user)

    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert len(resp['data']) == 1

    item = resp['data'][0]
    assert 'user_mis' in item
    assert 'missao' in item


async def test_list_pgts_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get(URL)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ============================================================
# Filtros
# ============================================================


async def test_filter_by_tipo_doc(client, session, token, users):
    """Testa filtro por tipo_doc."""
    user, _ = users

    await create_missao_with_user(session, user, tipo_doc='om', n_doc=101)
    await create_missao_with_user(session, user, tipo_doc='os', n_doc=102)

    response = await client.get(
        f'{URL}?tipo_doc=om',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['missao']['tipo_doc'] == 'om'


async def test_filter_by_multiple_tipo_doc(client, session, token, users):
    """Testa filtro por multiplos tipo_doc."""
    user, _ = users

    await create_missao_with_user(session, user, tipo_doc='om', n_doc=201)
    await create_missao_with_user(session, user, tipo_doc='os', n_doc=202)

    response = await client.get(
        f'{URL}?tipo_doc=om&tipo_doc=os',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 2


async def test_filter_by_n_doc(client, session, token, users):
    """Testa filtro por n_doc."""
    user, _ = users

    await create_missao_with_user(session, user, n_doc=300)
    await create_missao_with_user(session, user, n_doc=301)

    response = await client.get(
        f'{URL}?n_doc=300',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['missao']['n_doc'] == 300


async def test_filter_by_sit(client, session, token, users):
    """Testa filtro por situacao (sit)."""
    user, _ = users

    await create_missao_with_user(session, user, sit='c', n_doc=400)
    await create_missao_with_user(session, user, sit='d', n_doc=401)

    response = await client.get(
        f'{URL}?sit=c',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['user_mis']['sit'] == 'c'


async def test_filter_by_multiple_sit(client, session, token, users):
    """Testa filtro por multiplas situacoes."""
    user, _ = users

    await create_missao_with_user(session, user, sit='c', n_doc=410)
    await create_missao_with_user(session, user, sit='d', n_doc=411)
    await create_missao_with_user(session, user, sit='g', n_doc=412)

    response = await client.get(
        f'{URL}?sit=c&sit=d',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 2


async def test_filter_by_user_name(client, session, token, users):
    """Testa filtro por nome do usuario (busca parcial)."""
    user, other_user = users

    await create_missao_with_user(session, user, n_doc=500)
    await create_missao_with_user(session, other_user, n_doc=501)

    response = await client.get(
        f'{URL}?user={user.nome_guerra}',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1


async def test_filter_by_user_id(client, session, token, users):
    """Testa filtro por user_id."""
    user, other_user = users

    await create_missao_with_user(session, user, n_doc=510)
    await create_missao_with_user(session, other_user, n_doc=511)

    response = await client.get(
        f'{URL}?user_id={user.id}',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1


async def test_filter_by_tipo(client, session, token, users):
    """Testa filtro por tipo de missao."""
    user, _ = users

    await create_missao_with_user(session, user, tipo='adm', n_doc=600)
    await create_missao_with_user(session, user, tipo='opr', n_doc=601)

    response = await client.get(
        f'{URL}?tipo=adm',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['missao']['tipo'] == 'adm'


async def test_filter_by_multiple_tipo(client, session, token, users):
    """Testa filtro por multiplos tipos de missao."""
    user, _ = users

    await create_missao_with_user(session, user, tipo='adm', n_doc=610)
    await create_missao_with_user(session, user, tipo='opr', n_doc=611)
    await create_missao_with_user(session, user, tipo='tal', n_doc=612)

    response = await client.get(
        f'{URL}?tipo=adm&tipo=opr',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 2


# ============================================================
# Filtro por intervalo de datas
# ============================================================


async def test_filter_by_date_range(client, session, token, users):
    """Testa filtro por intervalo de datas (ini e fim)."""
    user, _ = users

    old_date = datetime(2024, 1, 15, 10, 0)
    recent_date = datetime(2024, 6, 15, 10, 0)

    await create_missao_with_user(
        session,
        user,
        afast=old_date,
        regres=old_date + timedelta(days=3),
        n_doc=700,
    )
    await create_missao_with_user(
        session,
        user,
        afast=recent_date,
        regres=recent_date + timedelta(days=3),
        n_doc=701,
    )

    response = await client.get(
        f'{URL}?ini=2024-06-01&fim=2024-07-01',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['missao']['n_doc'] == 701


async def test_filter_by_ini_only(client, session, token, users):
    """Testa filtro apenas com data inicial."""
    user, _ = users

    old_date = datetime(2023, 3, 10, 10, 0)
    recent_date = datetime(2024, 8, 10, 10, 0)

    await create_missao_with_user(
        session,
        user,
        afast=old_date,
        regres=old_date + timedelta(days=2),
        n_doc=710,
    )
    await create_missao_with_user(
        session,
        user,
        afast=recent_date,
        regres=recent_date + timedelta(days=2),
        n_doc=711,
    )

    response = await client.get(
        f'{URL}?ini=2024-01-01',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['missao']['n_doc'] == 711


async def test_filter_by_fim_only(client, session, token, users):
    """Testa filtro apenas com data final."""
    user, _ = users

    old_date = datetime(2023, 2, 5, 10, 0)
    recent_date = datetime(2024, 9, 5, 10, 0)

    await create_missao_with_user(
        session,
        user,
        afast=old_date,
        regres=old_date + timedelta(days=2),
        n_doc=720,
    )
    await create_missao_with_user(
        session,
        user,
        afast=recent_date,
        regres=recent_date + timedelta(days=2),
        n_doc=721,
    )

    response = await client.get(
        f'{URL}?fim=2023-12-31',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1
    assert resp['data'][0]['missao']['n_doc'] == 720


# ============================================================
# Paginacao
# ============================================================


async def test_pagination_defaults(client, session, token, users):
    """Testa paginacao com valores padrao (page=1, limit=20)."""
    user, _ = users

    for i in range(25):
        await create_missao_with_user(session, user, n_doc=800 + i)

    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 20
    assert resp['total'] == 25
    assert resp['page'] == 1
    assert resp['per_page'] == 20
    assert resp['pages'] == 2


async def test_pagination_custom_page_and_limit(
    client, session, token, users
):
    """Testa paginacao com page e limit customizados."""
    user, _ = users

    for i in range(15):
        await create_missao_with_user(session, user, n_doc=900 + i)

    response = await client.get(
        f'{URL}?page=2&limit=5',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 5
    assert resp['total'] == 15
    assert resp['page'] == 2
    assert resp['per_page'] == 5
    assert resp['pages'] == 3


async def test_pagination_last_page(client, session, token, users):
    """Testa ultima pagina com itens restantes."""
    user, _ = users

    for i in range(7):
        await create_missao_with_user(session, user, n_doc=950 + i)

    response = await client.get(
        f'{URL}?page=2&limit=5',
        headers=auth_header(token),
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 2
    assert resp['total'] == 7


# ============================================================
# Calculo de custos
# ============================================================


async def test_custo_missao_with_custos_jsonb(
    client, session, token, users
):
    """Testa que custos sao calculados corretamente a partir do JSONB."""
    user, _ = users

    custos_jsonb = {
        'total_dias': 5,
        'total_diarias': 4.5,
        'acrec_desloc_missao': 95,
        'totais_pg_sit': {
            f'pg_{user.p_g}_sit_c': {
                'total_valor': 1500.00,
            }
        },
    }

    await create_missao_with_user(
        session, user, n_doc=1000, custos=custos_jsonb
    )

    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1

    missao = resp['data'][0]['missao']
    assert missao['dias'] == 5
    assert missao['diarias'] == 4.5
    assert missao['valor_total'] == 1500.00
    assert missao['qtd_ac'] == 1


async def test_custo_missao_without_custos(client, session, token, users):
    """Testa que missao sem custos retorna valores zerados."""
    user, _ = users

    await create_missao_with_user(session, user, n_doc=1010)

    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 1

    missao = resp['data'][0]['missao']
    assert missao['dias'] == 0
    assert missao['diarias'] == 0
    assert missao['valor_total'] == 0
    assert missao['qtd_ac'] == 0


async def test_custo_missao_no_acrec_desloc(
    client, session, token, users
):
    """Testa que missao sem acrescimo de deslocamento tem qtd_ac=0."""
    user, _ = users

    custos_jsonb = {
        'total_dias': 3,
        'total_diarias': 2.5,
        'acrec_desloc_missao': 0,
        'totais_pg_sit': {
            f'pg_{user.p_g}_sit_c': {
                'total_valor': 800.00,
            }
        },
    }

    await create_missao_with_user(
        session, user, n_doc=1020, custos=custos_jsonb
    )

    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    missao = resp['data'][0]['missao']
    assert missao['qtd_ac'] == 0


# ============================================================
# Estrutura da resposta
# ============================================================


async def test_response_structure(client, session, token, users):
    """Testa que a estrutura de resposta esta correta."""
    user, _ = users

    await create_missao_with_user(session, user, n_doc=1100)

    response = await client.get(URL, headers=auth_header(token))

    assert response.status_code == HTTPStatus.OK
    resp = response.json()

    # Verifica campos da resposta paginada
    assert 'status' in resp
    assert 'data' in resp
    assert 'total' in resp
    assert 'page' in resp
    assert 'per_page' in resp
    assert 'pages' in resp

    item = resp['data'][0]

    # user_mis nao deve conter user_id e frag_id (excluidos no schema)
    assert 'user_id' not in item['user_mis']
    assert 'frag_id' not in item['user_mis']

    # missao nao deve conter users (excluido no schema)
    assert 'users' not in item['missao']

    # missao deve conter campos de custo
    assert 'dias' in item['missao']
    assert 'diarias' in item['missao']
    assert 'valor_total' in item['missao']
    assert 'qtd_ac' in item['missao']
