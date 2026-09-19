"""CRUD das missoes de GLE (/cegep/gle/missoes).

A missao guarda o trabalho da apuracao: os trechos de permanencia e os
militares. O **valor nao e gravado** — o backend recalcula a cada leitura a
partir do soldo vigente e da classificacao da localidade.
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.shared.estados_cidades import GrupoLocEsp

pytestmark = pytest.mark.anyio

URL = '/cegep/gle/missoes'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _payload(loc_id, user_id, **extra):
    corpo = {
        'descricao': 'OS 168-BAGL-26042026',
        'trechos': [
            {
                'loc_esp_id': loc_id,
                'chegada': '2026-04-26T14:15:00',
                'afastamento': '2026-05-29T02:35:00',
            }
        ],
        'militares_ids': [user_id],
    }
    corpo.update(extra)
    return corpo


async def test_cria_missao_com_trecho_e_militar(client, token, users, loc_a):
    user, _ = users

    resp = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['descricao'] == 'OS 168-BAGL-26042026'
    assert len(data['trechos']) == 1
    assert len(data['militares']) == 1
    assert data['percentual'] == '20%'


async def test_militares_sao_ordenados_por_antiguidade(
    client, token, users, loc_a, session
):
    """A lista segue a hierarquia militar, nunca nome ou ordem de inclusão.

    No seed, capitão tem `ant=7` e terceiro-sargento tem `ant=14`: o capitão
    deve vir primeiro mesmo com nome alfabeticamente posterior e tendo sido
    enviado por último.
    """
    junior, senior = users
    junior.p_g = '3s'
    junior.nome_guerra = 'ALFA'
    senior.p_g = 'cp'
    senior.nome_guerra = 'ZULU'
    await session.commit()
    await session.refresh(junior, attribute_names=['posto'])
    await session.refresh(senior, attribute_names=['posto'])

    criada = await client.post(
        URL,
        headers=_auth(token),
        json=_payload(
            loc_a.id,
            junior.id,
            militares_ids=[junior.id, senior.id],
        ),
    )
    assert criada.status_code == HTTPStatus.CREATED
    missao_id = criada.json()['data']['id']

    resp = await client.get(f'{URL}/{missao_id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert [m['user_id'] for m in resp.json()['data']['militares']] == [
        senior.id,
        junior.id,
    ]


async def test_missao_criada_aparece_na_lista(client, token, users, loc_a):
    user, _ = users
    await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )

    resp = await client.get(URL, headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    lista = resp.json()['data']
    assert len(lista) == 1
    assert lista[0]['total_trechos'] == 1
    assert lista[0]['total_militares'] == 1


async def test_valor_nao_e_gravado_e_sim_recalculado(
    client, token, users, loc_a
):
    """O GET devolve a apuracao mesmo sem ela ter sido gravada."""
    user, _ = users
    criada = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )
    missao_id = criada.json()['data']['id']

    resp = await client.get(f'{URL}/{missao_id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['multiplicador'] != '0'
    assert data['militares'][0]['valor'] != '0'


async def test_atualiza_substituindo_trechos(client, token, users, loc_a):
    user, _ = users
    criada = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )
    missao_id = criada.json()['data']['id']

    corpo = _payload(loc_a.id, user.id, descricao='OS 999-BAGL')
    corpo['trechos'].append({
        'loc_esp_id': loc_a.id,
        'chegada': '2026-07-01T06:00:00',
        'afastamento': '2026-07-10T20:00:00',
    })
    resp = await client.put(
        f'{URL}/{missao_id}', headers=_auth(token), json=corpo
    )

    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['descricao'] == 'OS 999-BAGL'
    assert len(data['trechos']) == 2


async def test_atualiza_mantendo_o_mesmo_militar(client, token, users, loc_a):
    """Reenviar o mesmo militar nao estoura `uq_militar_gle_missao_user`.

    Na mesma descarga o SQLAlchemy emitiria o INSERT antes do DELETE; o
    `flush` entre limpar e reinserir e o que evita a violacao.
    """
    user, _ = users
    criada = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )
    missao_id = criada.json()['data']['id']

    resp = await client.put(
        f'{URL}/{missao_id}',
        headers=_auth(token),
        json=_payload(loc_a.id, user.id, descricao='OS 168 revisada'),
    )

    assert resp.status_code == HTTPStatus.OK
    assert len(resp.json()['data']['militares']) == 1


async def test_atualiza_substituindo_militar_loga_snapshot(
    client, token, users, loc_a, session
):
    """Trocar o militar, sem mudar a contagem, entra na auditoria."""
    anterior, novo = users
    criada = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, anterior.id)
    )
    assert criada.status_code == HTTPStatus.CREATED
    missao_id = criada.json()['data']['id']

    resp = await client.put(
        f'{URL}/{missao_id}',
        headers=_auth(token),
        json=_payload(loc_a.id, novo.id),
    )

    assert resp.status_code == HTTPStatus.OK
    log = await session.scalar(
        select(UserActionLog).where(
            UserActionLog.resource == 'missao_gle',
            UserActionLog.resource_id == missao_id,
            UserActionLog.action == 'update',
        )
    )
    assert log is not None

    antes = json.loads(log.before)
    depois = json.loads(log.after)
    assert antes != depois
    assert antes['militares'] == [
        {'user_id': anterior.id, 'p_g': anterior.p_g}
    ]
    assert depois['militares'] == [{'user_id': novo.id, 'p_g': novo.p_g}]


async def test_remove_missao(client, token, users, loc_a):
    user, _ = users
    criada = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )
    missao_id = criada.json()['data']['id']

    resp = await client.delete(f'{URL}/{missao_id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    sumiu = await client.get(f'{URL}/{missao_id}', headers=_auth(token))
    assert sumiu.status_code == HTTPStatus.NOT_FOUND


async def test_remover_missao_preserva_a_localidade(
    client, token, users, loc_a, session
):
    """CASCADE apaga trechos e militares; a localidade e referencia."""
    user, _ = users
    criada = await client.post(
        URL, headers=_auth(token), json=_payload(loc_a.id, user.id)
    )
    await client.delete(
        f'{URL}/{criada.json()["data"]["id"]}', headers=_auth(token)
    )

    ainda_existe = await session.scalar(
        select(GrupoLocEsp).where(GrupoLocEsp.id == loc_a.id)
    )
    assert ainda_existe is not None


async def test_missao_inexistente_404(client, token):
    resp = await client.get(f'{URL}/999999', headers=_auth(token))

    assert resp.status_code == HTTPStatus.NOT_FOUND
