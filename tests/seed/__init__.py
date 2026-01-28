"""Seed data for tests.

Centraliza todos os objetos de seed que devem ser inseridos no banco de dados.
"""

from tests.seed.posto_grad import POSTOS_GRAD
from tests.seed.quads import QUADS_FUNCS, QUADS_GROUPS, QUADS_TYPES
from tests.seed.roles import ROLES

# Lista com todos os objetos a serem inseridos
# IMPORTANTE: A ordem importa devido às foreign keys
# NOTA: Estados e cidades são inseridos via conftest
# específico em tests/api/cities/
ALL_SEED_OBJECTS = [
    *POSTOS_GRAD,
    *ROLES,
    *QUADS_GROUPS,  # Deve vir antes de QUADS_TYPES
    *QUADS_TYPES,  # Deve vir antes de QUADS_FUNCS
    *QUADS_FUNCS,
]
