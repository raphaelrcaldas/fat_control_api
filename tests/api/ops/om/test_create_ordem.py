"""
Testes para o endpoint POST /ops/om/ (criacao de ordem de missao).

Testa criacao com etapas, validacoes de etapa e regras de negocio.
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.public.om import Etiqueta

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om/'


def _make_etapa(
    dt_dep='2025-06-15T10:00:00',
    dt_arr='2025-06-15T11:30:00',
    origem='SBGL',
    dest='SBBR',
    alternativa='SBCF',
    tvoo_alt=30,
    qtd_comb=15,
    esf_aer='normal',
):
    """Helper para criar payload de etapa."""
    return {
        'dt_dep': dt_dep,
        'origem': origem,
        'dest': dest,
        'dt_arr': dt_arr,
        'alternativa': alternativa,
        'tvoo_alt': tvoo_alt,
        'qtd_comb': qtd_comb,
        'esf_aer': esf_aer,
    }


def _make_ordem_payload(etapas=None, etiquetas_ids=None):
    """Helper para criar payload de ordem."""
    payload = {
        'matricula_anv': 2850,
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'uae': '1/1 GT',
        'esf_aer': 2,
        'campos_especiais': [],
        'etapas': etapas if etapas is not None else [],
        'tripulacao': None,
        'etiquetas_ids': etiquetas_ids or [],
    }
    return payload


async def test_create_ordem_success(client, session, token):
    """Criacao basica de ordem sem etapas."""
    payload = _make_ordem_payload()

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['numero'] == 'auto'
    assert data['status'] == 'rascunho'
    assert data['matricula_anv'] == 2850
    assert data['tipo'] == 'instrucao'
    assert data['projeto'] == 'KC-390'
    assert data['uae'] == '1/1 GT'


async def test_create_ordem_always_rascunho(
    client, session, token
):
    """Ordem criada sempre tem status rascunho."""
    payload = _make_ordem_payload()
    payload['status'] = 'aprovada'

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert data['status'] == 'rascunho'


async def test_create_ordem_always_auto_numero(
    client, session, token
):
    """Ordem criada sempre tem numero 'auto'."""
    payload = _make_ordem_payload()

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert data['numero'] == 'auto'


async def test_create_ordem_with_etapas(
    client, session, token
):
    """Criacao de ordem com etapas calcula tvoo_etp e data_saida."""
    etapa = _make_etapa()
    payload = _make_ordem_payload(etapas=[etapa])

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert len(data['etapas']) == 1
    assert data['etapas'][0]['origem'] == 'SBGL'
    assert data['etapas'][0]['dest'] == 'SBBR'
    assert data['etapas'][0]['tvoo_etp'] == 90
    assert data['data_saida'] == '2025-06-15'


async def test_create_ordem_with_etiquetas(
    client, session, token
):
    """Criacao de ordem com etiquetas vincula corretamente."""
    etiqueta = Etiqueta(
        nome='Prioridade', cor='#FF0000', descricao='alta'
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)

    payload = _make_ordem_payload(
        etiquetas_ids=[etiqueta.id]
    )

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert len(data['etiquetas']) == 1
    assert data['etiquetas'][0]['id'] == etiqueta.id


async def test_create_ordem_with_campos_especiais(
    client, session, token
):
    """Criacao de ordem com campos especiais."""
    payload = _make_ordem_payload()
    payload['campos_especiais'] = [
        {'label': 'Campo1', 'valor': 'Valor1'},
    ]

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert len(data['campos_especiais']) == 1
    assert data['campos_especiais'][0]['label'] == 'Campo1'


async def test_create_ordem_etapa_minutes_not_multiple_of_5(
    client, session, token
):
    """Etapa com minutos nao multiplos de 5 falha na validacao."""
    etapa = _make_etapa(
        dt_dep='2025-06-15T10:03:00',
        dt_arr='2025-06-15T11:30:00',
    )
    payload = _make_ordem_payload(etapas=[etapa])

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_ordem_etapa_arr_before_dep(
    client, session, token
):
    """Etapa com dt_arr <= dt_dep falha na validacao."""
    etapa = _make_etapa(
        dt_dep='2025-06-15T12:00:00',
        dt_arr='2025-06-15T11:00:00',
    )
    payload = _make_ordem_payload(etapas=[etapa])

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_ordem_etapa_tvoo_less_than_5_min(
    client, session, token
):
    """Etapa com tvoo_alt menor que 5 min falha na validacao."""
    etapa = _make_etapa(tvoo_alt=3)
    payload = _make_ordem_payload(etapas=[etapa])

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_ordem_etapa_tvoo_etp_less_than_5_min(
    client, session, token
):
    """Etapa com tvoo_etp calculado < 5 min falha."""
    etapa = _make_etapa(
        dt_dep='2025-06-15T10:00:00',
        dt_arr='2025-06-15T10:00:00',
    )
    payload = _make_ordem_payload(etapas=[etapa])

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_ordem_multiple_etapas(
    client, session, token
):
    """Criacao com multiplas etapas define data_saida da primeira."""
    etapa1 = _make_etapa(
        dt_dep='2025-06-16T08:00:00',
        dt_arr='2025-06-16T09:30:00',
        origem='SBGL',
        dest='SBBR',
    )
    etapa2 = _make_etapa(
        dt_dep='2025-06-15T14:00:00',
        dt_arr='2025-06-15T15:30:00',
        origem='SBBR',
        dest='SBCF',
    )
    payload = _make_ordem_payload(etapas=[etapa1, etapa2])

    response = await client.post(
        BASE_URL,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert len(data['etapas']) == 2
    assert data['data_saida'] == '2025-06-15'


async def test_create_ordem_requires_auth(client):
    """Endpoint requer autenticacao."""
    payload = _make_ordem_payload()
    response = await client.post(BASE_URL, json=payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
