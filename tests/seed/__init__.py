"""Seed data for tests.

Centraliza todos os objetos de seed que devem ser inseridos no banco de dados.
"""

from tests.seed.posto_grad import POSTOS_GRAD
from tests.seed.roles import ROLES

# Lista com todos os objetos a serem inseridos
ALL_SEED_OBJECTS = [
    *POSTOS_GRAD,
    *ROLES,
    # Adicione novos seeds aqui conforme necessário
    # *OUTROS_SEEDS,
]
