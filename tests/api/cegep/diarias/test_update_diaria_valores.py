"""
Testes para o endpoint PUT /cegep/diarias/valores/{valor_id}.

Este endpoint atualiza um valor de diaria existente.
Requer autenticacao.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from tests.factories import DiariaValorFactory

pytestmark = pytest.mark.anyio


async def test_update_diaria_valor_success(
    client, session, token, diaria_valores
):
    """Testa atualizacao de valor de diaria com sucesso."""
    valor = diaria_valores[0]

    update_data = {
        'valor': 380.00,
    }

    response = await client.put(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['valor'] == 380.00

    # Verifica no banco
    await session.refresh(valor)
    assert valor.valor == 380.00


async def test_update_diaria_valor_partial(
    client, session, token, diaria_valores
):
    """Testa atualizacao parcial de valor de diaria."""
    valor = diaria_valores[0]
    original_grupo_pg = valor.grupo_pg

    update_data = {
        'valor': 350.00,
    }

    response = await client.put(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que apenas valor foi alterado
    await session.refresh(valor)
    assert valor.grupo_pg == original_grupo_pg
    assert valor.valor == 350.00


async def test_update_diaria_valor_data_fim_before_data_inicio(
    client, token, diaria_valores
):
    """Testa que data_fim <= data_inicio falha na atualizacao."""
    valor = diaria_valores[0]

    update_data = {
        'data_fim': (valor.data_inicio - timedelta(days=1)).isoformat(),
    }

    response = await client.put(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_update_diaria_valor_data_inicio_after_existing_data_fim(
    client, token, diaria_valores
):
    """Testa que data_inicio > data_fim existente falha."""
    # Valor com data_fim definida (diaria_valores[1])
    valor = diaria_valores[1]  # Tem data_fim

    update_data = {
        'data_inicio': (valor.data_fim + timedelta(days=1)).isoformat(),
    }

    response = await client.put(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'Data fim deve ser maior' in response.json()['message']


async def test_update_diaria_valor_not_found(client, token):
    """Testa atualizacao de valor de diaria inexistente."""
    update_data = {
        'valor': 300.00,
    }

    response = await client.put(
        '/cegep/diarias/valores/999999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert 'não encontrado' in response.json()['message']


async def test_update_diaria_valor_without_token(client, diaria_valores):
    """Testa que requisicao sem token falha."""
    valor = diaria_valores[0]

    update_data = {
        'valor': 300.00,
    }

    response = await client.put(
        f'/cegep/diarias/valores/{valor.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_diaria_valor_estende_para_ocupado_conflito(
    client, session, token
):
    """Estender data_fim ate dentro de outra faixa da mesma chave -> 409.

    grupo_cid=4 (sem seed). Cria uma banda fechada em 2024 e uma aberta em
    2025 (adjacentes, sem overlap). Estender a fechada ate 2025 invade a
    aberta -> deve dar 409.
    """
    fechado = DiariaValorFactory(
        grupo_pg=1,
        grupo_cid=4,
        valor=300.00,
        data_inicio=date(2024, 1, 1),
        data_fim=date(2024, 12, 31),
    )
    aberto = DiariaValorFactory(
        grupo_pg=1,
        grupo_cid=4,
        valor=320.00,
        data_inicio=date(2025, 1, 1),
        data_fim=None,
    )
    session.add_all([fechado, aberto])
    await session.commit()
    await session.refresh(fechado)

    response = await client.put(
        f'/cegep/diarias/valores/{fechado.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'data_fim': '2025-06-01'},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'sobrep' in response.json()['message'].lower()


async def test_update_diaria_valor_apenas_valor_nao_dispara_overlap(
    client, session, token
):
    """Editar so o valor nao roda a checagem de sobreposicao.

    Mesmo com duas faixas legadas ja sobrepostas no banco (mesma chave),
    alterar apenas `valor` passa: o periodo nao muda.
    """
    a = DiariaValorFactory(
        grupo_pg=1,
        grupo_cid=4,
        valor=300.00,
        data_inicio=date(2025, 1, 1),
        data_fim=None,
    )
    b = DiariaValorFactory(
        grupo_pg=1,
        grupo_cid=4,
        valor=310.00,
        data_inicio=date(2025, 6, 1),
        data_fim=None,
    )
    session.add_all([a, b])
    await session.commit()
    await session.refresh(a)

    response = await client.put(
        f'/cegep/diarias/valores/{a.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={'valor': 305.00},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['valor'] == 305.00


async def test_update_diaria_valor_empty_body(
    client, session, token, diaria_valores
):
    """Testa atualizacao com body vazio nao altera nada."""
    valor = diaria_valores[0]
    original_valor = valor.valor

    response = await client.put(
        f'/cegep/diarias/valores/{valor.id}',
        headers={'Authorization': f'Bearer {token}'},
        json={},
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que nada foi alterado
    await session.refresh(valor)
    assert valor.valor == original_valor
