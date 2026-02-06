"""Seed data para estados e cidades.

Inclui todas as capitais estaduais para testes de diarias CEGEP.
Dados extraidos do Supabase em 2026-01-31.
"""

from fcontrol_api.models.public.estados_cidades import Cidade, Estado

ESTADOS_DATA = [
    # (codigo_uf, nome, uf)
    (12, 'Acre', 'AC'),
    (27, 'Alagoas', 'AL'),
    (16, 'Amapá', 'AP'),
    (13, 'Amazonas', 'AM'),
    (29, 'Bahia', 'BA'),
    (23, 'Ceará', 'CE'),
    (53, 'Distrito Federal', 'DF'),
    (32, 'Espírito Santo', 'ES'),
    (52, 'Goiás', 'GO'),
    (21, 'Maranhão', 'MA'),
    (51, 'Mato Grosso', 'MT'),
    (50, 'Mato Grosso do Sul', 'MS'),
    (31, 'Minas Gerais', 'MG'),
    (15, 'Pará', 'PA'),
    (25, 'Paraíba', 'PB'),
    (41, 'Paraná', 'PR'),
    (26, 'Pernambuco', 'PE'),
    (22, 'Piauí', 'PI'),
    (33, 'Rio de Janeiro', 'RJ'),
    (24, 'Rio Grande do Norte', 'RN'),
    (43, 'Rio Grande do Sul', 'RS'),
    (11, 'Rondônia', 'RO'),
    (14, 'Roraima', 'RR'),
    (42, 'Santa Catarina', 'SC'),
    (35, 'São Paulo', 'SP'),
    (28, 'Sergipe', 'SE'),
    (17, 'Tocantins', 'TO'),
]

ESTADOS = [
    Estado(codigo_uf=codigo_uf, nome=nome, uf=uf)
    for codigo_uf, nome, uf in ESTADOS_DATA
]

# Capitais estaduais (usadas nos grupos de cidade para diarias)
# e cidades adicionais para testes
CIDADES_DATA = [
    # (codigo, nome, uf)
    # Grupo 1 - Capitais especiais
    (1302603, 'Manaus', 'AM'),
    (3304557, 'Rio de Janeiro', 'RJ'),
    (3550308, 'São Paulo', 'SP'),
    (5300108, 'Brasília', 'DF'),
    # Grupo 2 - Demais capitais
    (1100205, 'Porto Velho', 'RO'),
    (1200401, 'Rio Branco', 'AC'),
    (1400100, 'Boa Vista', 'RR'),
    (1501402, 'Belém', 'PA'),
    (1600303, 'Macapá', 'AP'),
    (1721000, 'Palmas', 'TO'),
    (2111300, 'São Luís', 'MA'),
    (2211001, 'Teresina', 'PI'),
    (2304400, 'Fortaleza', 'CE'),
    (2408102, 'Natal', 'RN'),
    (2507507, 'João Pessoa', 'PB'),
    (2611606, 'Recife', 'PE'),
    (2704302, 'Maceió', 'AL'),
    (2800308, 'Aracaju', 'SE'),
    (2927408, 'Salvador', 'BA'),
    (3106200, 'Belo Horizonte', 'MG'),
    (3205309, 'Vitória', 'ES'),
    (4106902, 'Curitiba', 'PR'),
    (4205407, 'Florianópolis', 'SC'),
    (4314902, 'Porto Alegre', 'RS'),
    (5002704, 'Campo Grande', 'MS'),
    (5103403, 'Cuiabá', 'MT'),
    (5208707, 'Goiânia', 'GO'),
    # Cidades adicionais para testes (interior)
    (3509502, 'Campinas', 'SP'),
    (3518800, 'Guarulhos', 'SP'),
    (3301702, 'Duque de Caxias', 'RJ'),
    (3170206, 'Uberlândia', 'MG'),
]

CIDADES = [
    Cidade(codigo=codigo, nome=nome, uf=uf)
    for codigo, nome, uf in CIDADES_DATA
]
