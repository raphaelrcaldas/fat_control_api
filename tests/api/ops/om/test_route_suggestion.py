"""
Testes para o endpoint GET /ops/om/route-suggestions.

Este endpoint busca sugestões de rota baseada em missões anteriores,
realizando duas buscas separadas:
1. Por rota completa (origem + dest): tvoo_etp, qtd_comb
2. Por destino apenas: alternativa, tvoo_alt
"""

from http import HTTPStatus

import pytest

from tests.factories import OrdemEtapaFactory, OrdemMissaoFactory

pytestmark = pytest.mark.anyio


async def test_route_suggestion_full_match(
    client, session, users, token
):
    """Rota completa (origem + dest) retorna todos os campos."""
    user, _ = users

    # Criar ordem aprovada com etapa SBGL -> SBBR
    ordem = OrdemMissaoFactory(created_by=user.id, status='aprovada')
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(
        ordem_id=ordem.id,
        origem='SBGL',
        dest='SBBR',
        alternativa='SBCF',
        tvoo_etp=90,
        tvoo_alt=45,
        qtd_comb=15,
    )
    session.add(etapa)
    await session.commit()

    # Buscar sugestão para a mesma rota
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGL', 'dest': 'SBBR'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica dados da rota completa
    assert data['has_route_data'] is True
    assert data['origem'] == 'SBGL'
    assert data['tvoo_etp'] == 90
    assert data['qtd_comb'] == 15

    # Verifica dados do destino
    assert data['has_destination_data'] is True
    assert data['dest'] == 'SBBR'
    assert data['alternativa'] == 'SBCF'
    assert data['tvoo_alt'] == 45


async def test_route_suggestion_partial_match_dest_only(
    client, session, users, token
):
    """Rota inexistente mas destino visitado retorna dados parciais."""
    user, _ = users

    # Criar ordem aprovada com etapa SBRF -> SBBR (não SBGL)
    ordem = OrdemMissaoFactory(created_by=user.id, status='aprovada')
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(
        ordem_id=ordem.id,
        origem='SBRF',  # Origem diferente
        dest='SBBR',  # Mesmo destino
        alternativa='SBCF',
        tvoo_etp=120,
        tvoo_alt=45,
        qtd_comb=18,
    )
    session.add(etapa)
    await session.commit()

    # Buscar sugestão para rota SBGL -> SBBR (origem diferente)
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGL', 'dest': 'SBBR'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Dados da rota completa NÃO disponíveis
    assert data['has_route_data'] is False
    assert data['origem'] is None
    assert data['tvoo_etp'] is None
    assert data['qtd_comb'] is None

    # Dados do destino disponíveis
    assert data['has_destination_data'] is True
    assert data['dest'] == 'SBBR'
    assert data['alternativa'] == 'SBCF'
    assert data['tvoo_alt'] == 45


async def test_route_suggestion_no_match(
    client, session, users, token
):
    """Nem rota nem destino existem, retorna None."""
    user, _ = users

    # Criar ordem aprovada com etapa diferente
    ordem = OrdemMissaoFactory(created_by=user.id, status='aprovada')
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(
        ordem_id=ordem.id,
        origem='SBRF',
        dest='SBSV',  # Destino diferente
        alternativa='SBCF',
    )
    session.add(etapa)
    await session.commit()

    # Buscar sugestão para rota/destino inexistentes
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGL', 'dest': 'SBJD'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] is None


async def test_route_suggestion_ignores_rascunho(
    client, session, users, token
):
    """Ordens com status 'rascunho' sao ignoradas na busca."""
    user, _ = users

    # Criar ordem RASCUNHO com etapa
    ordem = OrdemMissaoFactory(created_by=user.id, status='rascunho')
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(
        ordem_id=ordem.id,
        origem='SBGL',
        dest='SBBR',
        alternativa='SBCF',
    )
    session.add(etapa)
    await session.commit()

    # Buscar sugestão - deve retornar None (rascunho ignorado)
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGL', 'dest': 'SBBR'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] is None


async def test_route_suggestion_invalid_icao(client, token):
    """Codigos ICAO invalidos (nao 4 caracteres) retornam None."""
    # ICAO com menos de 4 caracteres
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SB', 'dest': 'SBBR'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] is None

    # ICAO com mais de 4 caracteres
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGLX', 'dest': 'SBBR'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] is None


async def test_route_suggestion_case_insensitive(
    client, session, users, token
):
    """A busca deve ser case-insensitive (sbgl == SBGL)."""
    user, _ = users

    # Criar ordem com ICAO em maiúsculas
    ordem = OrdemMissaoFactory(
        created_by=user.id, status='aprovada'
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(
        ordem_id=ordem.id,
        origem='SBGL',
        dest='SBBR',
        alternativa='SBCF',
    )
    session.add(etapa)
    await session.commit()

    # Buscar com minúsculas
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'sbgl', 'dest': 'sbbr'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data is not None
    assert data['has_route_data'] is True
    assert data['has_destination_data'] is True


async def test_route_suggestion_returns_most_recent(
    client, session, users, token
):
    """Multiplas etapas para mesma rota retorna a mais recente."""
    user, _ = users

    # Criar ordem antiga
    ordem_antiga = OrdemMissaoFactory(
        created_by=user.id, status='aprovada'
    )
    session.add(ordem_antiga)
    await session.commit()
    await session.refresh(ordem_antiga)

    etapa_antiga = OrdemEtapaFactory(
        ordem_id=ordem_antiga.id,
        origem='SBGL',
        dest='SBBR',
        alternativa='SBSP',  # Alternativa antiga
        tvoo_alt=30,
        qtd_comb=10,
    )
    session.add(etapa_antiga)
    await session.commit()

    # Criar ordem mais recente
    ordem_recente = OrdemMissaoFactory(
        created_by=user.id, status='aprovada'
    )
    session.add(ordem_recente)
    await session.commit()
    await session.refresh(ordem_recente)

    etapa_recente = OrdemEtapaFactory(
        ordem_id=ordem_recente.id,
        origem='SBGL',
        dest='SBBR',
        alternativa='SBCF',  # Alternativa mais recente
        tvoo_alt=45,
        qtd_comb=15,
    )
    session.add(etapa_recente)
    await session.commit()

    # Buscar sugestão - deve retornar dados da mais recente
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGL', 'dest': 'SBBR'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']

    # Verifica que retornou dados da ordem mais recente
    assert data['alternativa'] == 'SBCF'
    assert data['tvoo_alt'] == 45
    assert data['qtd_comb'] == 15


async def test_route_suggestion_requires_auth(client):
    """Endpoint requer autenticacao (token JWT)."""
    response = await client.get(
        '/ops/om/route-suggestions',
        params={'origem': 'SBGL', 'dest': 'SBBR'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
