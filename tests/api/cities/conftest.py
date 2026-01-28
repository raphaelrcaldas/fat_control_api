"""
Fixtures específicas para testes de cities.

Garante que estados sejam inseridos antes de cidades.
"""

import pytest

from fcontrol_api.models.public.estados_cidades import Cidade, Estado


@pytest.fixture(autouse=True)
async def seed_estados_cidades(session):
    """Insere estados e cidades na ordem correta."""
    # Cria objetos novos para cada teste (evita problemas de sessão)
    estados = [
        Estado(codigo_uf=35, nome='São Paulo', uf='SP'),
        Estado(codigo_uf=33, nome='Rio de Janeiro', uf='RJ'),
        Estado(codigo_uf=31, nome='Minas Gerais', uf='MG'),
        Estado(codigo_uf=53, nome='Distrito Federal', uf='DF'),
    ]

    cidades = [
        Cidade(codigo=3550308, nome='São Paulo', uf='SP'),
        Cidade(codigo=3509502, nome='Campinas', uf='SP'),
        Cidade(codigo=3518800, nome='Guarulhos', uf='SP'),
        Cidade(codigo=3304557, nome='Rio de Janeiro', uf='RJ'),
        Cidade(codigo=3301702, nome='Duque de Caxias', uf='RJ'),
        Cidade(codigo=3106200, nome='Belo Horizonte', uf='MG'),
        Cidade(codigo=3170206, nome='Uberlândia', uf='MG'),
        Cidade(codigo=5300108, nome='Brasília', uf='DF'),
    ]

    # Insere estados primeiro
    session.add_all(estados)
    await session.flush()

    # Depois insere cidades
    session.add_all(cidades)
    await session.flush()
