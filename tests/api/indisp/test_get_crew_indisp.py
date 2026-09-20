"""
Testes para o endpoint GET /indisp/.

Este endpoint retorna indisponibilidades de tripulantes filtrados por
função (funcao) e pela unidade ativa do token (active_org).
Requer autenticação (middleware global) e organização ativa no token.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.operacao import Operacao, OperacaoPessoal
from tests.factories import IndispFactory, OperacaoFactory, TripFactory

pytestmark = pytest.mark.anyio


async def test_get_crew_indisp_success(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa listagem de indisponibilidades de tripulantes com sucesso."""
    user, _ = users
    trip, func = trip_with_func

    # Cria uma indisp para o tripulante
    indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
    )
    session.add(indisp)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['trip']['id'] == trip.id


async def test_get_crew_indisp_response_structure(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa estrutura correta da resposta (trip, indisps)."""
    user, _ = users
    trip, func = trip_with_func

    indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
    )
    session.add(indisp)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1

    item = data[0]
    assert 'trip' in item
    assert 'indisps' in item
    assert item['elegivel_desadaptacao'] is True
    assert item['restricoes_derivadas'] == [
        {
            'origem': 'cemal',
            'codigo': 'cemal_ausente',
            'inicio': None,
            'fim': None,
            'efeito': 'bloqueio',
            'rotulo': None,
            'operacao_id': None,
        }
    ]

    # Estrutura do trip
    trip_data = item['trip']
    assert 'id' in trip_data
    assert 'trig' in trip_data
    assert 'user' in trip_data
    assert 'func' in trip_data

    # Estrutura do user dentro do trip
    user_data = trip_data['user']
    assert 'id' in user_data
    assert 'nome_guerra' in user_data


async def test_get_crew_indisp_no_trips_returns_empty(client, token_sem_perm):
    """Testa que sem tripulantes retorna lista vazia."""
    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil'},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_get_crew_indisp_excludes_inactive_users(
    client, session, users, token_sem_perm
):
    """Testa que usuários inativos não são retornados."""
    user, other_user = users

    # Cria trip para o user inativo
    other_user.active = False
    await session.commit()

    trip = TripFactory(
        user_id=other_user.id, uae='11gt', active=True, func='pil'
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil'},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_get_crew_indisp_excludes_inactive_trips(
    client, session, users, token_sem_perm
):
    """Testa que tripulantes inativos não são retornados."""
    user, _ = users

    trip = TripFactory(user_id=user.id, uae='11gt', active=False, func='pil')
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil'},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []


async def test_get_crew_indisp_filters_old_indisps(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa que indisps com mais de 30 dias são filtradas."""
    user, _ = users
    trip, func = trip_with_func

    # Indisp antiga (mais de 30 dias)
    old_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=60),
        date_end=date.today() - timedelta(days=35),
    )
    # Indisp recente
    new_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=10),
        date_end=date.today() + timedelta(days=5),
    )

    session.add_all([old_indisp, new_indisp])
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1

    indisps = data[0]['indisps']
    assert len(indisps) == 1
    # Verifica que apenas a indisp recente foi retornada
    indisp_ids = [i['id'] for i in indisps]
    assert new_indisp.id in indisp_ids
    assert old_indisp.id not in indisp_ids


async def test_get_crew_indisp_trip_without_indisps(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa que tripulante sem indisps retorna lista vazia de indisps."""
    trip, func = trip_with_func

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['indisps'] == []


async def test_get_crew_indisp_groups_indisps_by_user(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa que múltiplas indisps de um usuário são agrupadas."""
    user, _ = users
    trip, func = trip_with_func

    # Cria múltiplas indisps para o mesmo usuário
    indisp1 = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        mtv='fer',
    )
    indisp2 = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() + timedelta(days=10),
        date_end=date.today() + timedelta(days=15),
        mtv='svc',
    )

    session.add_all([indisp1, indisp2])
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1  # Apenas um tripulante

    indisps = data[0]['indisps']
    assert len(indisps) == 2  # Duas indisps agrupadas


async def test_get_crew_indisp_indisps_ordered_by_date_end_desc(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa que indisps são ordenadas por date_end desc dentro do grupo."""
    user, _ = users
    trip, func = trip_with_func

    old_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today() - timedelta(days=10),
        date_end=date.today() - timedelta(days=5),
    )
    new_indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
    )

    session.add_all([old_indisp, new_indisp])
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    indisps = data[0]['indisps']
    # Mais recente primeiro
    assert indisps[0]['id'] == new_indisp.id
    assert indisps[1]['id'] == old_indisp.id


async def test_get_crew_indisp_filters_by_funcao(
    client, session, users, token_sem_perm
):
    """Testa que filtro por funcao funciona corretamente."""
    user, other_user = users

    # Tripulante com função 'pil'
    trip_pil = TripFactory(
        user_id=user.id, uae='11gt', active=True, func='pil'
    )
    session.add(trip_pil)
    await session.commit()
    await session.refresh(trip_pil)

    # Tripulante de outra função ('mc'): 'func' virou FK para `funcoes.cod`,
    # entao o contraste tem de usar uma funcao do catalogo.
    trip_mc = TripFactory(
        user_id=other_user.id, uae='11gt', active=True, func='mc'
    )
    session.add(trip_mc)
    await session.commit()
    await session.refresh(trip_mc)

    # Busca apenas pilotos
    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil'},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['trip']['id'] == trip_pil.id


async def test_get_crew_indisp_scoped_by_active_org(
    client, session, users, token_sem_perm
):
    """Testa que a lente por active_org isola tripulantes de outra unidade.

    O token_sem_perm carrega active_org='11gt', então apenas tripulantes dessa
    unidade são retornados — os da '1gt' ficam de fora.
    """
    user, other_user = users

    # Tripulante na unidade ativa ('11gt') — deve aparecer
    trip_11gt = TripFactory(
        user_id=user.id, uae='11gt', active=True, func='pil'
    )
    session.add(trip_11gt)
    await session.commit()
    await session.refresh(trip_11gt)

    # Tripulante em outra unidade ('1gt') — deve ser excluído
    trip_1gt = TripFactory(
        user_id=other_user.id, uae='1gt', active=True, func='pil'
    )
    session.add(trip_1gt)
    await session.commit()
    await session.refresh(trip_1gt)

    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil'},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1
    assert data[0]['trip']['id'] == trip_11gt.id


async def test_get_crew_indisp_func_in_response(
    client, session, users, trip_with_func, token_sem_perm
):
    """Testa que a função é incluída na resposta."""
    trip, func = trip_with_func

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert len(data) == 1

    # Função achatada no próprio tripulante (1:1)
    assert data[0]['trip']['func'] == func.func
    assert data[0]['trip']['oper'] == func.oper


async def test_get_crew_indisp_without_token_fails(client):
    """Testa que requisição sem token falha."""
    response = await client.get(
        '/indisp/',
        params={'funcao': 'pil'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def _operacao_com_militar(
    session,
    *,
    user_id: int,
    criador_id: int,
    ingresso: date,
    regresso: date,
    status: str = 'andamento',
    uae: str = '11gt',
    nome: str | None = None,
) -> Operacao:
    """Cria uma operação com um militar no efetivo, para a faixa derivada."""
    op = OperacaoFactory(created_by=criador_id, status=status, uae=uae)
    if nome is not None:
        op.nome = nome
    session.add(op)
    await session.commit()
    await session.refresh(op)

    session.add(
        OperacaoPessoal(
            operacao_id=op.id,
            user_id=user_id,
            func='Tripulante',
            sit='d',
            data_ingresso=ingresso,
            data_regresso=regresso,
        )
    )
    await session.commit()
    return op


def _restricoes_de_operacao(payload: dict) -> list[dict]:
    item = payload['data'][0]
    return [
        r for r in item['restricoes_derivadas'] if r['origem'] == 'operacao'
    ]


async def test_militar_em_operacao_vira_faixa_derivada(
    client, session, users, trip_with_func, token_sem_perm
):
    """A operação do efetivo vira restrição derivada, sem virar indisp."""
    user, _ = users
    trip, func = trip_with_func

    op = await _operacao_com_militar(
        session,
        user_id=user.id,
        criador_id=user.id,
        ingresso=date(2025, 6, 2),
        regresso=date(2025, 6, 8),
        nome='SLOP TESTE',
    )

    response = await client.get(
        '/indisp/',
        params={
            'funcao': func.func,
            'date_from': '2025-06-01',
            'date_to': '2025-06-30',
        },
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    (restricao,) = _restricoes_de_operacao(response.json())
    assert restricao['codigo'] == 'operacao'
    assert restricao['efeito'] == 'bloqueio'
    assert restricao['inicio'] == '2025-06-02'
    assert restricao['fim'] == '2025-06-08'
    assert restricao['rotulo'] == 'SLOP TESTE'
    assert restricao['operacao_id'] == op.id


async def test_operacao_cancelada_nao_gera_faixa(
    client, session, users, trip_with_func, token_sem_perm
):
    """Cancelada não tira ninguém da unidade."""
    user, _ = users
    trip, func = trip_with_func

    await _operacao_com_militar(
        session,
        user_id=user.id,
        criador_id=user.id,
        ingresso=date(2025, 6, 2),
        regresso=date(2025, 6, 8),
        status='cancelada',
    )

    response = await client.get(
        '/indisp/',
        params={
            'funcao': func.func,
            'date_from': '2025-06-01',
            'date_to': '2025-06-30',
        },
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert _restricoes_de_operacao(response.json()) == []


async def test_periodo_fora_da_janela_nao_gera_faixa(
    client, session, users, trip_with_func, token_sem_perm
):
    """A janela pedida recorta: operação de julho não aparece em junho."""
    user, _ = users
    trip, func = trip_with_func

    await _operacao_com_militar(
        session,
        user_id=user.id,
        criador_id=user.id,
        ingresso=date(2025, 7, 10),
        regresso=date(2025, 7, 20),
    )

    response = await client.get(
        '/indisp/',
        params={
            'funcao': func.func,
            'date_from': '2025-06-01',
            'date_to': '2025-06-30',
        },
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert _restricoes_de_operacao(response.json()) == []


async def test_operacao_de_outra_unidade_nao_vaza(
    client, session, users, trip_with_func, token_sem_perm
):
    """Operação de outra `uae` não entra na grade desta unidade.

    O filtro de org dos chamadores é no TRIPULANTE, e o `user_id` que sai dali
    é global — sem o escopo por `uae` na query, o nome de uma operação alheia
    apareceria aqui, com deeplink que cai no 404 de `_get_op`.
    """
    user, _ = users
    trip, func = trip_with_func

    await _operacao_com_militar(
        session,
        user_id=user.id,
        criador_id=user.id,
        ingresso=date(2025, 6, 2),
        regresso=date(2025, 6, 8),
        uae='1gt',
        nome='OPERACAO ALHEIA',
    )

    response = await client.get(
        '/indisp/',
        params={
            'funcao': func.func,
            'date_from': '2025-06-01',
            'date_to': '2025-06-30',
        },
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert _restricoes_de_operacao(response.json()) == []


async def test_get_crew_indisp_com_obs_nula(
    client, session, users, trip_with_func, token_sem_perm
):
    """Indisponibilidade sem observação não pode quebrar a serialização.

    `obs` é a única coluna anulável de `indisps`, e o PATCH trata um None
    explícito como "limpar a observação" — logo `NULL` é estado válido no
    banco e `IndispOut` tem de aceitá-lo.
    """
    user, _ = users
    trip, func = trip_with_func

    indisp = IndispFactory(
        user_id=user.id,
        created_by=user.id,
        date_start=date.today(),
        date_end=date.today() + timedelta(days=5),
        obs=None,
    )
    session.add(indisp)
    await session.commit()

    response = await client.get(
        '/indisp/',
        params={'funcao': func.func},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data[0]['indisps'][0]['obs'] is None
