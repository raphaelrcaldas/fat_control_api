"""Valor apurado da GLE ponta a ponta.

O caso de ouro e o da planilha GLEE que esta calculadora substitui: Boa
Vista/RR (grupo A), 26/04/2026 14:15 -> 29/05/2026 02:35, que da 33 dias,
multiplicador 0.21397849 e R$ 1.281,30 para um 1S (soldo 5988,00).
"""

from datetime import date
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.shared.posto_grad import Soldo
from tests.factories import SoldoFactory

pytestmark = pytest.mark.anyio

URL = '/cegep/gle/missoes'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _criar(client, token, corpo):
    resp = await client.post(URL, headers=_auth(token), json=corpo)
    assert resp.status_code == HTTPStatus.CREATED, resp.text
    return resp.json()['data']


@pytest.fixture
async def militar_1s(session, users):
    """Fixa o posto: `UserFactory.p_g` e sorteado e o soldo mudaria."""
    user, _ = users
    user.p_g = '1s'
    await session.commit()
    return user


async def test_caso_real_da_planilha(client, token, militar_1s, loc_a):
    """33 dias, 0.21397849 e R$ 1.281,30 — o caso de referencia."""
    data = await _criar(
        client,
        token,
        {
            'descricao': 'OS 168-BAGL-26042026',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-04-26T14:15:00',
                    'afastamento': '2026-05-29T02:35:00',
                }
            ],
            'militares_ids': [militar_1s.id],
        },
    )

    assert data['trechos'][0]['dias_contados'] == 33
    assert data['multiplicador'] == '0.21397849'
    assert data['percentual'] == '20%'
    assert data['militares'][0]['valor'] == '1281.30'
    assert data['militares'][0]['soldo'] == '5988.00'


async def test_soldo_ref_usa_primeiro_dia_pago_entre_trechos(
    client, token, session, militar_1s, loc_a
):
    """A referência usa o menor dia pago, não a ordem dos trechos."""
    soldo_anterior = await session.scalar(
        select(Soldo).where(
            Soldo.pg == '1s',
            Soldo.data_inicio == date(2026, 1, 1),
        )
    )
    assert soldo_anterior is not None
    soldo_anterior.data_fim = date(2026, 5, 9)
    session.add(
        SoldoFactory(
            pg='1s',
            valor=Decimal('9999.00'),
            data_inicio=date(2026, 5, 10),
            data_fim=None,
        )
    )
    await session.commit()

    data = await _criar(
        client,
        token,
        {
            'descricao': 'trechos fora de ordem com reajuste',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-05-20T06:00:00',
                    'afastamento': '2026-05-22T20:00:00',
                },
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-04-26T14:15:00',
                    'afastamento': '2026-04-29T02:35:00',
                },
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-05-10T06:00:00',
                    'afastamento': '2026-05-12T20:00:00',
                },
            ],
            'militares_ids': [militar_1s.id],
        },
    )

    assert data['militares'][0]['soldo'] == '5988.00'
    assert data['militares'][0]['valor'] == '506.82'


async def test_grupo_b_paga_metade_do_grupo_a(
    client, token, militar_1s, loc_a, loc_b
):
    """Mesmo periodo, categorias diferentes: B = 10%, A = 20%."""
    periodo = {
        'chegada': '2026-06-01T06:00:00',
        'afastamento': '2026-06-11T20:00:00',
    }
    em_a = await _criar(
        client,
        token,
        {
            'descricao': 'A',
            'trechos': [{'loc_esp_id': loc_a.id, **periodo}],
            'militares_ids': [militar_1s.id],
        },
    )
    em_b = await _criar(
        client,
        token,
        {
            'descricao': 'B',
            'trechos': [{'loc_esp_id': loc_b.id, **periodo}],
            'militares_ids': [militar_1s.id],
        },
    )

    assert em_a['percentual'] == '20%'
    assert em_b['percentual'] == '10%'
    dobro = Decimal(em_b['militares'][0]['valor']) * 2
    assert Decimal(em_a['militares'][0]['valor']) == dobro


async def test_antisobreposicao_paga_o_dia_uma_vez_so(
    client, token, militar_1s, loc_a, loc_b
):
    """Dia coberto por A e por B fica com o A; no B aparece zerado.

    O dia zerado continua na memoria de calculo, marcado como duplicado:
    o usuario precisa ver que ele foi considerado e por que nao pagou.
    """
    data = await _criar(
        client,
        token,
        {
            'descricao': 'OS com sobreposicao',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-06-01T06:00:00',
                    'afastamento': '2026-06-10T20:00:00',
                },
                {
                    'loc_esp_id': loc_b.id,
                    'chegada': '2026-06-10T06:00:00',
                    'afastamento': '2026-06-15T20:00:00',
                },
            ],
            'militares_ids': [militar_1s.id],
        },
    )

    assert data['percentual'] == '20% e 10%'
    trecho_b = data['trechos'][1]
    dia_10 = [d for d in trecho_b['dias'] if d['data'] == '2026-06-10'][0]
    assert dia_10['duplicado'] is True
    assert Decimal(dia_10['fator']) == 0
    # O dia 10 aparece nos dois trechos, mas so conta no primeiro.
    trecho_a = data['trechos'][0]
    pago = [d for d in trecho_a['dias'] if d['data'] == '2026-06-10'][0]
    assert pago['duplicado'] is False


async def test_regra_das_8_horas_na_ponta(client, token, militar_1s, loc_a):
    """Chegada as 16:00 conta (8h exatas); as 16:01 nao."""
    conta = await _criar(
        client,
        token,
        {
            'descricao': '8h exatas',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-06-01T16:00:00',
                    'afastamento': '2026-06-05T20:00:00',
                }
            ],
            'militares_ids': [militar_1s.id],
        },
    )
    nao_conta = await _criar(
        client,
        token,
        {
            'descricao': '7h59',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-06-01T16:01:00',
                    'afastamento': '2026-06-05T20:00:00',
                }
            ],
            'militares_ids': [militar_1s.id],
        },
    )

    assert conta['trechos'][0]['dias_contados'] == 5
    assert nao_conta['trechos'][0]['dias_contados'] == 4


async def test_soldo_do_posto_define_o_valor(
    client, token, session, users, loc_a
):
    """Mesmo multiplicador, soldos diferentes: o valor acompanha o posto."""
    user, outro = users
    user.p_g = '1s'  # soldo 5988,00
    outro.p_g = '2s'  # soldo 5209,00
    outro.unidade = '11gt'
    await session.commit()

    data = await _criar(
        client,
        token,
        {
            'descricao': 'dois postos',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-04-26T14:15:00',
                    'afastamento': '2026-05-29T02:35:00',
                }
            ],
            'militares_ids': [user.id, outro.id],
        },
    )

    por_pg = {m['p_g']: Decimal(m['valor']) for m in data['militares']}
    assert por_pg['1s'] == Decimal('1281.30')
    assert por_pg['2s'] < por_pg['1s']


async def test_p_g_gravado_e_snapshot_e_nao_segue_promocao(
    client, token, session, militar_1s, loc_a
):
    """Promover o militar depois nao reescreve a apuracao ja feita."""
    data = await _criar(
        client,
        token,
        {
            'descricao': 'antes da promocao',
            'trechos': [
                {
                    'loc_esp_id': loc_a.id,
                    'chegada': '2026-04-26T14:15:00',
                    'afastamento': '2026-05-29T02:35:00',
                }
            ],
            'militares_ids': [militar_1s.id],
        },
    )
    missao_id = data['id']

    militar_1s.p_g = 'so'  # promovido depois da apuracao
    await session.commit()

    resp = await client.get(f'{URL}/{missao_id}', headers=_auth(token))

    assert resp.json()['data']['militares'][0]['p_g'] == '1s'
