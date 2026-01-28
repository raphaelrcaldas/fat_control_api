from fcontrol_api.models.public.estados_cidades import Cidade, Estado

ESTADOS_DATA = [
    (35, 'São Paulo', 'SP'),
    (33, 'Rio de Janeiro', 'RJ'),
    (31, 'Minas Gerais', 'MG'),
    (53, 'Distrito Federal', 'DF'),
]

ESTADOS = [
    Estado(codigo_uf=codigo_uf, nome=nome, uf=uf)
    for codigo_uf, nome, uf in ESTADOS_DATA
]

CIDADES_DATA = [
    (3550308, 'São Paulo', 'SP'),
    (3509502, 'Campinas', 'SP'),
    (3518800, 'Guarulhos', 'SP'),
    (3304557, 'Rio de Janeiro', 'RJ'),
    (3301702, 'Duque de Caxias', 'RJ'),
    (3106200, 'Belo Horizonte', 'MG'),
    (3170206, 'Uberlândia', 'MG'),
    (5300108, 'Brasília', 'DF'),
]

CIDADES = [
    Cidade(codigo=codigo, nome=nome, uf=uf)
    for codigo, nome, uf in CIDADES_DATA
]
