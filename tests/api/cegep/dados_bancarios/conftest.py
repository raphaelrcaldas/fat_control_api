"""
Fixtures para testes de Dados Bancarios.
"""

import pytest

from tests.factories import DadosBancariosFactory


@pytest.fixture
async def dados_bancarios(session, users):
    """
    Cria dados bancarios para o primeiro usuario.

    Returns:
        DadosBancarios: Instancia de dados bancarios
    """
    user, _ = users

    dados = DadosBancariosFactory(
        user_id=user.id,
        banco='Banco do Brasil',
        codigo_banco='001',
        agencia='1234-5',
        conta='12345-6',
    )

    session.add(dados)
    await session.commit()
    await session.refresh(dados)

    return dados
