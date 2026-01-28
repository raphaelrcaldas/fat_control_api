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


class TestRouteSuggestionEndpoint:
    """Testes para GET /ops/om/route-suggestions"""

    async def test_route_suggestion_full_match(
        self, client, session, users, token
    ):
        """
        Quando uma rota completa (origem + dest) existe,
        retorna todos os campos com has_route_data=True e
        has_destination_data=True.
        """
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
        data = response.json()

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
        self, client, session, users, token
    ):
        """
        Quando a rota completa NÃO existe, mas o destino já foi visitado,
        retorna has_route_data=False e has_destination_data=True,
        com alternativa e tvoo_alt preenchidos.
        """
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
        data = response.json()

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
        self, client, session, users, token
    ):
        """
        Quando nem a rota nem o destino existem, retorna None.
        """
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
        assert response.json() is None

    async def test_route_suggestion_ignores_rascunho(
        self, client, session, users, token
    ):
        """
        Ordens com status 'rascunho' são ignoradas na busca.
        """
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
        assert response.json() is None

    async def test_route_suggestion_invalid_icao(self, client, token):
        """
        Códigos ICAO inválidos (não 4 caracteres) retornam None.
        """
        # ICAO com menos de 4 caracteres
        response = await client.get(
            '/ops/om/route-suggestions',
            params={'origem': 'SB', 'dest': 'SBBR'},
            headers={'Authorization': f'Bearer {token}'},
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json() is None

        # ICAO com mais de 4 caracteres
        response = await client.get(
            '/ops/om/route-suggestions',
            params={'origem': 'SBGLX', 'dest': 'SBBR'},
            headers={'Authorization': f'Bearer {token}'},
        )

        assert response.status_code == HTTPStatus.OK
        assert response.json() is None

    async def test_route_suggestion_case_insensitive(
        self, client, session, users, token
    ):
        """
        A busca deve ser case-insensitive (sbgl == SBGL).
        """
        user, _ = users

        # Criar ordem com ICAO em maiúsculas
        ordem = OrdemMissaoFactory(created_by=user.id, status='aprovada')
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
        data = response.json()
        assert data is not None
        assert data['has_route_data'] is True
        assert data['has_destination_data'] is True

    async def test_route_suggestion_returns_most_recent(
        self, client, session, users, token
    ):
        """
        Quando existem múltiplas etapas para a mesma rota,
        retorna os dados da mais recente.
        """
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
        data = response.json()

        # Verifica que retornou dados da ordem mais recente
        assert data['alternativa'] == 'SBCF'
        assert data['tvoo_alt'] == 45
        assert data['qtd_comb'] == 15

    async def test_route_suggestion_requires_auth(self, client):
        """
        Endpoint requer autenticação (token JWT).
        """
        response = await client.get(
            '/ops/om/route-suggestions',
            params={'origem': 'SBGL', 'dest': 'SBBR'},
        )

        assert response.status_code == HTTPStatus.UNAUTHORIZED
