"""Contratos do cadastro global de localidades e de seus ICAOs."""

import json
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.logs import UserActionLog
from tests.factories import LocEspIcaoFactory

pytestmark = pytest.mark.anyio
URL = '/cegep/gle'


async def test_crud_icaos_e_auditoria(client, token, session):
    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'cidade_id': 1400100,
        'grupo': 1,
        'fuso': -4,
        'icaos': ['sbbv', 'SBBR'],
    }
    criada = await client.post(URL, headers=headers, json=payload)
    assert criada.status_code == HTTPStatus.CREATED
    data = criada.json()['data']
    assert data['icaos'] == ['SBBR', 'SBBV']
    assert data['cidade']['codigo'] == payload['cidade_id']

    atualizada = await client.put(
        f'{URL}/{data["id"]}',
        headers=headers,
        json={**payload, 'icaos': ['SBBV', 'SBGL']},
    )
    assert atualizada.status_code == HTTPStatus.OK
    assert atualizada.json()['data']['icaos'] == ['SBBV', 'SBGL']
    log = await session.scalar(
        select(UserActionLog).where(
            UserActionLog.resource == 'loc_esp',
            UserActionLog.resource_id == data['id'],
            UserActionLog.action == 'update',
        )
    )
    assert json.loads(log.before)['icaos'] == ['SBBR', 'SBBV']
    assert json.loads(log.after)['icaos'] == ['SBBV', 'SBGL']

    pesquisa = await client.get(
        URL, headers=headers, params={'search': 'BGL', 'grupo': 1, 'uf': 'rr'}
    )
    assert pesquisa.status_code == HTTPStatus.OK
    assert [item['id'] for item in pesquisa.json()['data']] == [data['id']]

    removida = await client.delete(f'{URL}/{data["id"]}', headers=headers)
    assert removida.status_code == HTTPStatus.OK
    ausente = await client.get(f'{URL}/{data["id"]}', headers=headers)
    assert ausente.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    ('cidade_id', 'icaos', 'status'),
    [
        (9999999, [], HTTPStatus.UNPROCESSABLE_ENTITY),
        (1400100, [], HTTPStatus.CONFLICT),
        (1721000, ['SBBV'], HTTPStatus.CONFLICT),
    ],
)
async def test_referencias_invalidas(
    client, token, loc_a_com_icao, cidade_id, icaos, status
):
    response = await client.post(
        URL,
        headers={'Authorization': f'Bearer {token}'},
        json={'cidade_id': cidade_id, 'grupo': 2, 'fuso': -3, 'icaos': icaos},
    )
    assert response.status_code == status


async def test_update_recusa_icao_ocupado_sem_alterar(
    client, token, session, loc_a_com_icao, loc_b
):
    session.add(LocEspIcaoFactory(loc_esp_id=loc_b.id, icao='SBPJ'))
    await session.commit()
    await session.refresh(loc_b, ['icaos'])
    headers = {'Authorization': f'Bearer {token}'}
    response = await client.put(
        f'{URL}/{loc_b.id}',
        headers=headers,
        json={
            'cidade_id': loc_b.cidade_id,
            'grupo': 2,
            'fuso': -3,
            'icaos': ['SBBV'],
        },
    )
    assert response.status_code == HTTPStatus.CONFLICT
    atual = await client.get(f'{URL}/{loc_b.id}', headers=headers)
    assert atual.json()['data']['icaos'] == ['SBPJ']


async def test_catalogo_global_sem_org_ativa(client, token_sistema, loc_a):
    response = await client.get(
        URL, headers={'Authorization': f'Bearer {token_sistema}'}
    )
    assert response.status_code == HTTPStatus.OK
    assert loc_a.id in [item['id'] for item in response.json()['data']]
