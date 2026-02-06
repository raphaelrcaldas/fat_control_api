"""Seed data para diarias CEGEP.

Inclui grupos de cidade, grupos de P/G e valores de diarias.
Dados extraidos do Supabase em 2026-01-31.
"""

from datetime import date

from fcontrol_api.models.cegep.diarias import DiariaValor, GrupoCidade, GrupoPg

# Grupos de Cidade
# Grupo 1: Capitais especiais (SP, RJ, BSB, Manaus)
# Grupo 2: Demais capitais
# Grupo 3: Demais localidades (calculado, nao tem cadastro)
GRUPOS_CIDADE_DATA = [
    # (grupo, cidade_id)
    # Grupo 1 - Capitais especiais
    (1, 1302603),  # Manaus
    (1, 3304557),  # Rio de Janeiro
    (1, 3550308),  # Sao Paulo
    (1, 5300108),  # Brasilia
    # Grupo 2 - Demais capitais
    (2, 1100205),  # Porto Velho
    (2, 1200401),  # Rio Branco
    (2, 1400100),  # Boa Vista
    (2, 1501402),  # Belem
    (2, 1600303),  # Macapa
    (2, 1721000),  # Palmas
    (2, 2111300),  # Sao Luis
    (2, 2211001),  # Teresina
    (2, 2304400),  # Fortaleza
    (2, 2408102),  # Natal
    (2, 2507507),  # Joao Pessoa
    (2, 2611606),  # Recife
    (2, 2704302),  # Maceio
    (2, 2800308),  # Aracaju
    (2, 2927408),  # Salvador
    (2, 3106200),  # Belo Horizonte
    (2, 3205309),  # Vitoria
    (2, 4106902),  # Curitiba
    (2, 4205407),  # Florianopolis
    (2, 4314902),  # Porto Alegre
    (2, 5002704),  # Campo Grande
    (2, 5103403),  # Cuiaba
    (2, 5208707),  # Goiania
]

GRUPOS_CIDADE = [
    GrupoCidade(grupo=grupo, cidade_id=cidade_id)
    for grupo, cidade_id in GRUPOS_CIDADE_DATA
]

# Grupos de P/G (Posto/Graduacao)
# Grupo 1: Oficiais Generais
# Grupo 2: Oficiais Superiores
# Grupo 3: Oficiais Intermediarios/Subalternos e Graduados
# Grupo 4: Pracas
GRUPOS_PG_DATA = [
    # (grupo, pg_short)
    # Grupo 1 - Oficiais Generais
    (1, 'br'),
    (1, 'mb'),
    (1, 'tb'),
    # Grupo 2 - Oficiais Superiores
    (2, 'cl'),
    (2, 'mj'),
    (2, 'tc'),
    # Grupo 3 - Oficiais Int/Sub e Graduados
    (3, '1s'),
    (3, '1t'),
    (3, '2s'),
    (3, '2t'),
    (3, '3s'),
    (3, 'cp'),
    (3, 'so'),
    # Grupo 4 - Pracas
    (4, 'cb'),
    (4, 's1'),
    (4, 's2'),
]

GRUPOS_PG = [
    GrupoPg(grupo=grupo, pg_short=pg_short)
    for grupo, pg_short in GRUPOS_PG_DATA
]

# Valores de Diarias (grupo_pg x grupo_cid)
# Valores vigentes a partir de 2025-01-01
DIARIAS_VALOR_DATA = [
    # (grupo_pg, grupo_cid, valor, data_inicio, data_fim)
    # Grupo PG 1 (Oficiais Generais)
    (1, 1, 600.00, date(2025, 1, 1), None),
    (1, 2, 515.00, date(2025, 1, 1), None),
    (1, 3, 455.00, date(2025, 1, 1), None),
    # Grupo PG 2 (Oficiais Superiores)
    (2, 1, 510.00, date(2025, 1, 1), None),
    (2, 2, 450.00, date(2025, 1, 1), None),
    (2, 3, 395.00, date(2025, 1, 1), None),
    # Grupo PG 3 (Oficiais Int/Sub e Graduados)
    (3, 1, 425.00, date(2025, 1, 1), None),
    (3, 2, 380.00, date(2025, 1, 1), None),
    (3, 3, 335.00, date(2025, 1, 1), None),
    # Grupo PG 4 (Pracas)
    (4, 1, 355.00, date(2025, 1, 1), None),
    (4, 2, 315.00, date(2025, 1, 1), None),
    (4, 3, 280.00, date(2025, 1, 1), None),
]

DIARIAS_VALOR = [
    DiariaValor(
        grupo_pg=grupo_pg,
        grupo_cid=grupo_cid,
        valor=valor,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    for grupo_pg, grupo_cid, valor, data_inicio, data_fim in DIARIAS_VALOR_DATA
]
