"""Seed data for tests.

Centraliza todos os objetos de seed que devem ser inseridos no banco.
Os objetos sao agrupados por ordem de dependencia de FK.
"""

from tests.seed.diarias import DIARIAS_VALOR, GRUPOS_CIDADE, GRUPOS_PG
from tests.seed.estados_cidades import CIDADES, ESTADOS
from tests.seed.posto_grad import POSTOS_GRAD
from tests.seed.quads import QUADS_FUNCS, QUADS_GROUPS, QUADS_TYPES
from tests.seed.roles import ROLES
from tests.seed.soldos import SOLDOS

# Grupos de seed ordenados por dependencia de FK
# Cada grupo deve ser inserido e commitado/flushed antes do proximo
SEED_GROUPS = [
    # Grupo 1: Tabelas base sem dependencias
    [*ESTADOS, *POSTOS_GRAD, *ROLES, *QUADS_GROUPS],
    # Grupo 2: Dependem do Grupo 1
    [*CIDADES, *SOLDOS, *QUADS_TYPES],
    # Grupo 3: Dependem do Grupo 2
    [*GRUPOS_CIDADE, *GRUPOS_PG, *QUADS_FUNCS],
    # Grupo 4: Dependem do Grupo 3
    [*DIARIAS_VALOR],
]

# Mantido para compatibilidade (nao recomendado usar diretamente)
ALL_SEED_OBJECTS = [
    item
    for group in SEED_GROUPS
    for item in group
]
