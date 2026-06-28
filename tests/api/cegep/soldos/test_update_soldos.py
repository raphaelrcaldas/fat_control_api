"""
Testes para o endpoint PUT /cegep/soldos/{soldo_id}.

Este endpoint atualiza um soldo existente.
Requer autenticacao.
"""

from datetime import date, timedelta
from decimal import Decimal
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.posto_grad import Soldo

pytestmark = pytest.mark.anyio


async def test_update_soldo_success(client, session, token, soldos):
    """Testa atualizacao de soldo com sucesso."""
    soldo = soldos[0]

    update_data = {
        'valor': 5500.00,
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['valor'] == 5500.00

    # Verifica no banco
    await session.refresh(soldo)
    assert soldo.valor == 5500.00


async def test_update_soldo_partial(client, session, token, soldos):
    """Testa atualizacao parcial de soldo."""
    soldo = soldos[0]
    original_pg = soldo.pg

    update_data = {
        'valor': 4800.00,
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que apenas valor foi alterado
    await session.refresh(soldo)
    assert soldo.pg == original_pg
    assert soldo.valor == 4800.00


async def test_update_soldo_change_posto_conflito(
    client, session, token, soldos
):
    """Mudar pg para um posto com vigencia aberta sobreposta -> 409.

    soldos[0] (cb) cobre [hoje-30, aberto]. O seed ja tem 3s vigente desde
    2026-01-01 (aberto). Re-chavear cb -> 3s mantendo o periodo aberto cria
    duas faixas 3s sobrepostas: a protecao deve barrar com 409.
    """
    soldo = soldos[0]

    update_data = {
        'pg': '3s',  # Muda de cb para 3s (slot ja ocupado e vigente)
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'sobrep' in response.json()['message'].lower()


async def test_update_soldo_change_posto_slot_livre(
    client, session, token, soldos
):
    """Mudar pg para um periodo passado que nao sobrepoe nada -> 200.

    Move soldos[0] (cb) para 3s mas numa janela fechada em 2024, que nao
    cruza a vigencia aberta do 3s (seed, desde 2026-01-01).
    """
    soldo = soldos[0]

    update_data = {
        'pg': '3s',
        'data_inicio': '2024-01-01',
        'data_fim': '2024-12-31',
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['pg'] == '3s'


async def test_update_soldo_estende_para_periodo_ocupado_conflito(
    client, session, token
):
    """Estender data_fim para dentro de outra vigencia da mesma chave -> 409.

    Cria uma faixa cb fechada no passado (sem cruzar o seed cb, aberto desde
    2026-01-01) e tenta estende-la ate 2026-06-01, invadindo a vigencia
    aberta do seed.
    """
    band = Soldo(
        pg='cb',
        valor=Decimal('2500.00'),
        data_inicio=date(2024, 1, 1),
        data_fim=date(2024, 12, 31),
    )
    session.add(band)
    await session.commit()
    await session.refresh(band)

    response = await client.put(
        f'/cegep/soldos/{band.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'data_fim': '2026-06-01'},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'sobrep' in response.json()['message'].lower()


async def test_update_soldo_apenas_valor_nao_dispara_overlap(
    client, session, token
):
    """Editar so o valor nao roda a checagem de sobreposicao.

    Mesmo havendo no banco faixas legadas que ja se sobrepoem (seed cb aberto
    + esta banda que cruza o seed), uma edicao apenas de `valor` deve passar:
    o periodo nao muda, logo nao ha conflito novo a barrar.
    """
    band = Soldo(
        pg='cb',
        valor=Decimal('2500.00'),
        data_inicio=date(2026, 3, 1),
        data_fim=date(2026, 9, 30),  # sobrepoe o seed cb (aberto)
    )
    session.add(band)
    await session.commit()
    await session.refresh(band)

    response = await client.put(
        f'/cegep/soldos/{band.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'valor': 2600.00},
    )

    assert response.status_code == HTTPStatus.OK
    await session.refresh(band)
    assert band.valor == Decimal('2600.00')


async def test_update_soldo_invalid_posto(client, token, soldos):
    """Testa que posto/graduacao invalido falha."""
    soldo = soldos[0]

    update_data = {
        'pg': 'XX',  # Posto invalido
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Posto/Graduacao invalido' in response.json()['message']


async def test_update_soldo_data_fim_before_data_inicio(client, token, soldos):
    """Testa que data_fim <= data_inicio falha na atualizacao."""
    soldo = soldos[0]

    update_data = {
        'data_fim': (soldo.data_inicio - timedelta(days=1)).isoformat(),
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_update_soldo_data_inicio_after_existing_data_fim(
    client, token, soldos
):
    """Testa que data_inicio > data_fim existente falha."""
    # Soldo com data_fim definida (soldos[1])
    soldo = soldos[1]  # 2s com data_fim

    update_data = {
        'data_inicio': (soldo.data_fim + timedelta(days=1)).isoformat(),
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_update_soldo_not_found(client, token):
    """Testa atualizacao de soldo inexistente."""
    update_data = {
        'valor': 5000.00,
    }

    response = await client.put(
        '/cegep/soldos/999999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'Soldo nao encontrado' in response.json()['message']


async def test_update_soldo_without_token(client, soldos):
    """Testa que requisicao sem token falha."""
    soldo = soldos[0]

    update_data = {
        'valor': 5000.00,
    }

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_soldo_empty_body(client, session, token, soldos):
    """Testa atualizacao com body vazio nao altera nada."""
    soldo = soldos[0]
    original_valor = soldo.valor

    response = await client.put(
        f'/cegep/soldos/{soldo.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que nada foi alterado
    await session.refresh(soldo)
    assert soldo.valor == original_valor
