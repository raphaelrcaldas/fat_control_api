"""
Testes para o endpoint GET /cegep/missoes/.

Este endpoint lista missoes com filtros avancados e paginacao.
Requer autenticacao.
"""

from datetime import date, datetime, time, timedelta
from http import HTTPStatus

import pytest

from fcontrol_api.models.cegep.missoes import FragEtiqueta
from tests.factories import (
    EtiquetaFactory,
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio


async def test_list_missoes_success(client, token, missao_existente):
    """Testa listagem de missoes sem filtros."""
    response = await client.get(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['total'] >= 1
    assert len(resp['data']) >= 1


async def test_list_missoes_without_token(client):
    """Testa que requisicao sem token falha."""
    response = await client.get('/cegep/missoes/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_list_missoes_pagination(client, session, token, users):
    """Testa paginacao de missoes."""
    user, _ = users
    today = date.today()

    # Criar 5 missoes
    for i in range(5):
        missao = FragMisFactory(
            n_doc=5000 + i,
            afast=datetime.combine(today + timedelta(days=i * 10), time(8, 0)),
            regres=datetime.combine(
                today + timedelta(days=i * 10 + 3), time(18, 0)
            ),
        )
        session.add(missao)
        await session.flush()

        pernoite = PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308,
            data_ini=today + timedelta(days=i * 10),
            data_fim=today + timedelta(days=i * 10 + 3),
        )
        session.add(pernoite)

        user_frag = UserFragFactory(
            frag_id=missao.id, user_id=user.id, sit='d', p_g=user.p_g
        )
        session.add(user_frag)

    await session.commit()

    # Pagina 1 com 2 itens
    response = await client.get(
        '/cegep/missoes/',
        params={'page': 1, 'per_page': 2},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert len(resp['data']) == 2
    assert resp['page'] == 1
    assert resp['per_page'] == 2


async def test_list_missoes_filter_tipo_doc(client, token, missao_existente):
    """Testa filtro por tipo_doc."""
    response = await client.get(
        '/cegep/missoes/',
        params={'tipo_doc': 'om'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    for missao in resp['data']:
        assert missao['tipo_doc'] == 'om'


async def test_list_missoes_filter_n_doc(client, token, missao_existente):
    """Testa filtro por n_doc."""
    response = await client.get(
        '/cegep/missoes/',
        params={'n_doc': 1001},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] >= 1
    for missao in resp['data']:
        assert missao['n_doc'] == 1001


async def test_list_missoes_filter_tipo(client, token, missao_existente):
    """Testa filtro por tipo de missao."""
    response = await client.get(
        '/cegep/missoes/',
        params={'tipo': 'adm'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    for missao in resp['data']:
        assert missao['tipo'] == 'adm'


async def test_list_missoes_filter_date_range(client, token, missao_existente):
    """Testa filtro por intervalo de datas."""
    today = date.today()
    ini = (today + timedelta(days=5)).isoformat()
    fim = (today + timedelta(days=20)).isoformat()

    response = await client.get(
        '/cegep/missoes/',
        params={'ini': ini, 'fim': fim},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    # A missao_existente esta entre dias 10 e 15
    assert resp['total'] >= 1


async def test_list_missoes_filter_user_search(
    client, token, missao_existente, users
):
    """Testa filtro por nome de guerra."""
    user, _ = users

    response = await client.get(
        '/cegep/missoes/',
        params={'user_search': user.nome_guerra[:5]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] >= 1


async def test_list_missoes_filter_city(client, token, missao_existente):
    """Testa filtro por cidade."""
    response = await client.get(
        '/cegep/missoes/',
        params={'city': 'Paulo'},  # Sao Paulo
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] >= 1


async def test_list_missoes_filter_etiqueta_ids(
    client, session, token, missao_existente
):
    """Testa filtro por etiquetas."""
    # Criar etiqueta e associar a missao
    etiqueta = EtiquetaFactory(nome='Filtro Test')
    session.add(etiqueta)
    await session.flush()

    frag_etiq = FragEtiqueta(
        frag_id=missao_existente.id, etiqueta_id=etiqueta.id
    )
    session.add(frag_etiq)
    await session.commit()

    response = await client.get(
        '/cegep/missoes/',
        params={'etiqueta_ids': str(etiqueta.id)},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] >= 1


async def test_list_missoes_multiple_filters(client, token, missao_existente):
    """Testa multiplos filtros combinados."""
    today = date.today()

    response = await client.get(
        '/cegep/missoes/',
        params={
            'tipo_doc': 'om',
            'tipo': 'adm',
            'ini': (today + timedelta(days=5)).isoformat(),
            'fim': (today + timedelta(days=20)).isoformat(),
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    for missao in resp['data']:
        assert missao['tipo_doc'] == 'om'
        assert missao['tipo'] == 'adm'


async def test_list_missoes_per_page_max(client, token, missao_existente):
    """Testa que per_page e limitado a 100."""
    response = await client.get(
        '/cegep/missoes/',
        params={'per_page': 200},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_list_missoes_empty_result(client, token):
    """Testa listagem quando nao ha missoes no filtro."""
    response = await client.get(
        '/cegep/missoes/',
        params={'n_doc': 999999},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 0
    assert resp['data'] == []


async def test_list_missoes_invalid_etiqueta_ids(
    client, token, missao_existente
):
    """Testa que etiqueta_ids invalido e ignorado."""
    response = await client.get(
        '/cegep/missoes/',
        params={'etiqueta_ids': '99999'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    # Deve retornar vazio pois nao existe etiqueta 99999
    assert resp['total'] == 0
